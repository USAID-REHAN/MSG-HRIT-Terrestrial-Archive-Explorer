"""Background job orchestration for discovery / sampling / download / processing."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select

from app.config import get_settings
from app.db.models import Job
from app.db.session import session_scope
from app.discovery.crawler import discover_archive
from app.disk_usage import invalidate_disk_usage_cache
from app.downloader.worker import run_download_worker
from app.processing.pipeline import run_processing_worker
from app.sampling.selector import apply_sample_selection

logger = logging.getLogger(__name__)


PIPELINE_PHASES = ("discovery", "sampling", "download", "processing")


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._stop_flags: dict[str, threading.Event] = {}
        self._active_job_ids: dict[str, int] = {}
        # Phases currently owned by a running pipeline (blocks overlapping starts)
        self._pipeline_phases: set[str] = set()

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def _create_job(self, job_type: str, scope: str) -> int:
        with session_scope() as db:
            job = Job(
                job_type=job_type,
                scope=scope,
                status="queued",
                progress_current=0,
                progress_total=0,
                started_at=None,
                finished_at=None,
                log_summary="Queued",
            )
            db.add(job)
            db.flush()
            return job.id

    def _update_job(self, job_id: int, **fields: Any) -> None:
        with session_scope() as db:
            job = db.get(Job, job_id)
            if job is None:
                return
            for k, v in fields.items():
                setattr(job, k, v)

    def _make_progress(self, job_id: int):
        lock = threading.Lock()
        last_write = 0.0
        last_current = -1

        def progress(current: int, total: int, message: str) -> None:
            nonlocal last_write, last_current
            now = time.monotonic()
            terminal = total >= 0 and current >= total
            with lock:
                if (
                    not terminal
                    and current == last_current
                    and now - last_write < get_settings().job_progress_min_interval_seconds
                ):
                    return
                if (
                    not terminal
                    and last_write
                    and now - last_write < get_settings().job_progress_min_interval_seconds
                ):
                    return
                last_write = now
                last_current = current
            self._update_job(
                job_id,
                progress_current=current,
                progress_total=total,
                log_summary=message,
                status="running",
            )

        return progress

    def reconcile_interrupted_jobs(self) -> int:
        """Mark jobs abandoned by a previous backend process as paused."""
        now = self._utcnow()
        with session_scope() as db:
            rows = list(
                db.execute(select(Job).where(Job.status.in_(["queued", "running"])))
                .scalars()
                .all()
            )
            for job in rows:
                job.status = "paused"
                job.finished_at = now
                job.log_summary = "Interrupted by backend restart; safe to resume"
            return len(rows)

    def is_running(self, job_type: str) -> bool:
        t = self._threads.get(job_type)
        if t is not None and t.is_alive():
            return True
        if job_type in self._pipeline_phases:
            return True
        return False

    def request_pause(self, job_type: str) -> bool:
        # Pausing any pipeline phase also pauses the parent pipeline job
        flag = self._stop_flags.get(job_type)
        if flag is None and job_type in PIPELINE_PHASES:
            flag = self._stop_flags.get("pipeline")
        if flag is None:
            return False
        flag.set()
        jid = self._active_job_ids.get(job_type)
        if jid:
            self._update_job(jid, status="paused", log_summary="Pause requested…")
        pipe_id = self._active_job_ids.get("pipeline")
        if pipe_id and job_type != "pipeline":
            self._update_job(
                pipe_id, status="paused", log_summary=f"Pause requested during {job_type}…"
            )
        return True

    def start_discovery(self) -> dict:
        return self._start("discovery", "full catalog", self._run_discovery)

    def start_sampling(self) -> dict:
        return self._start("sampling", "sample selection", self._run_sampling)

    def start_download(self) -> dict:
        return self._start("download", "sample queue", self._run_download)

    def start_processing(self, timeslot_ids: Optional[list[int]] = None) -> dict:
        scope = (
            f"timeslots {timeslot_ids}"
            if timeslot_ids
            else "downloaded timeslots"
        )

        def runner(job_id: int, stop: threading.Event) -> None:
            self._run_processing(job_id, stop, timeslot_ids)

        return self._start("processing", scope, runner)

    def start_pipeline(self) -> dict:
        """One-click: discovery → sampling → download → processing (sequential)."""
        with self._lock:
            blockers = [
                jt
                for jt in ("pipeline", *PIPELINE_PHASES)
                if self.is_running(jt)
            ]
            if blockers:
                return {
                    "ok": False,
                    "error": (
                        "Cannot start pipeline while already running: "
                        + ", ".join(blockers)
                    ),
                    "job_id": self._active_job_ids.get("pipeline")
                    or self._active_job_ids.get(blockers[0]),
                }
        return self._start(
            "pipeline",
            "discover → sample → download → process",
            self._run_pipeline,
        )

    def retry_download(self, timeslot_id: int) -> dict:
        from app.db.models import Timeslot

        with session_scope() as db:
            ts = db.get(Timeslot, timeslot_id)
            if ts is None:
                return {"ok": False, "error": "Timeslot not found"}
            if ts.sample_role is None:
                return {"ok": False, "error": "Timeslot was not selected for download"}
            ts.download_status = "queued"
            ts.last_error = None
        return self.start_download()

    def retry_processing(self, timeslot_id: int) -> dict:
        from app.db.models import Product
        from sqlalchemy import delete

        with session_scope() as db:
            db.execute(delete(Product).where(Product.timeslot_id == timeslot_id))
        return self.start_processing([timeslot_id])

    def _start(self, job_type: str, scope: str, runner) -> dict:
        with self._lock:
            if self.is_running(job_type):
                return {
                    "ok": False,
                    "error": f"{job_type} job already running",
                    "job_id": self._active_job_ids.get(job_type),
                }
            # Individual steps must not overlap a running one-click pipeline
            if job_type in PIPELINE_PHASES and self.is_running("pipeline"):
                return {
                    "ok": False,
                    "error": "pipeline job already running — pause it first or wait",
                    "job_id": self._active_job_ids.get("pipeline"),
                }
            job_id = self._create_job(job_type, scope)
            stop = threading.Event()
            self._stop_flags[job_type] = stop
            self._active_job_ids[job_type] = job_id

            def target() -> None:
                try:
                    self._update_job(
                        job_id,
                        status="running",
                        started_at=self._utcnow(),
                        log_summary=f"Starting {job_type}…",
                    )
                    runner(job_id, stop)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("%s job failed", job_type)
                    self._update_job(
                        job_id,
                        status="failed",
                        finished_at=self._utcnow(),
                        log_summary=str(exc),
                    )
                finally:
                    with self._lock:
                        self._threads.pop(job_type, None)
                        if job_type == "pipeline":
                            self._pipeline_phases.clear()

            t = threading.Thread(target=target, name=f"job-{job_type}", daemon=True)
            self._threads[job_type] = t
            t.start()
            return {"ok": True, "job_id": job_id, "job_type": job_type}

    def _job_status(self, job_id: int) -> Optional[str]:
        with session_scope() as db:
            job = db.get(Job, job_id)
            return job.status if job else None

    def _run_pipeline(self, job_id: int, stop: threading.Event) -> None:
        """Run the four pipeline phases in order; reuses existing step runners."""
        phase_runners = [
            ("discovery", self._run_discovery),
            ("sampling", self._run_sampling),
            ("download", self._run_download),
            ("processing", lambda jid, s: self._run_processing(jid, s, None)),
        ]
        total = len(phase_runners)

        for idx, (phase, runner) in enumerate(phase_runners, start=1):
            if stop.is_set():
                self._update_job(
                    job_id,
                    status="paused",
                    finished_at=self._utcnow(),
                    progress_current=idx - 1,
                    progress_total=total,
                    log_summary=f"Paused before {phase}",
                )
                return

            self._update_job(
                job_id,
                status="running",
                progress_current=idx - 1,
                progress_total=total,
                log_summary=f"Phase {idx}/{total}: {phase}…",
            )

            child_id = self._create_job(phase, f"pipeline phase {idx}/{total}")
            with self._lock:
                self._pipeline_phases.add(phase)
                self._stop_flags[phase] = stop
                self._active_job_ids[phase] = child_id

            try:
                self._update_job(
                    child_id,
                    status="running",
                    started_at=self._utcnow(),
                    log_summary=f"Pipeline phase {idx}/{total}: {phase}",
                )
                runner(child_id, stop)
            finally:
                with self._lock:
                    self._pipeline_phases.discard(phase)
                    # Keep pipeline stop flag; clear phase alias only
                    if self._stop_flags.get(phase) is stop:
                        self._stop_flags.pop(phase, None)

            child_status = self._job_status(child_id)
            if child_status == "failed":
                with session_scope() as db:
                    child = db.get(Job, child_id)
                    detail = child.log_summary if child else "unknown error"
                self._update_job(
                    job_id,
                    status="failed",
                    finished_at=self._utcnow(),
                    progress_current=idx,
                    progress_total=total,
                    log_summary=f"Failed during {phase}: {detail}",
                )
                return
            if child_status == "paused" or stop.is_set():
                self._update_job(
                    job_id,
                    status="paused",
                    finished_at=self._utcnow(),
                    progress_current=idx,
                    progress_total=total,
                    log_summary=f"Paused during {phase}",
                )
                return

        self._update_job(
            job_id,
            status="completed",
            finished_at=self._utcnow(),
            progress_current=total,
            progress_total=total,
            log_summary="Pipeline complete: discovery → sample → download → process",
        )

    def _run_discovery(self, job_id: int, stop: threading.Event) -> None:
        progress = self._make_progress(job_id)
        with session_scope() as db:
            result = discover_archive(db, get_settings(), progress=progress)
        if stop.is_set():
            self._update_job(
                job_id,
                status="paused",
                finished_at=self._utcnow(),
                log_summary=f"Paused. {result}",
            )
            return
        self._update_job(
            job_id,
            status="completed",
            finished_at=self._utcnow(),
            log_summary=(
                f"Catalogued +{result['new_timeslots']} new "
                f"({result['updated_timeslots']} refreshed) across "
                f"{result['dates_scanned']} dates"
            ),
            progress_current=result["dates_scanned"],
            progress_total=result["dates_scanned"],
        )

    def _run_sampling(self, job_id: int, stop: threading.Event) -> None:
        progress = self._make_progress(job_id)
        with session_scope() as db:
            result = apply_sample_selection(db, get_settings(), progress=progress)
        self._update_job(
            job_id,
            status="completed",
            finished_at=self._utcnow(),
            log_summary=(
                f"Selected {result['total_selected']} timeslots "
                f"(~{result['total_selected_bytes'] / (1024**3):.2f} GB)"
            ),
            progress_current=result["dates_considered"],
            progress_total=result["dates_considered"],
        )

    def _run_download(self, job_id: int, stop: threading.Event) -> None:
        progress = self._make_progress(job_id)
        result = run_download_worker(
            get_settings(),
            progress=progress,
            stop_flag=stop.is_set,
        )
        if result.get("paused_for_disk"):
            status = "paused"
            msg = "; ".join(result.get("messages") or ["Paused — low disk space"])
        elif result.get("stopped_by_user"):
            status = "paused"
            msg = "Paused by user"
        else:
            status = "completed"
            msg = (
                f"Download finished: {result['attempted']} attempted, "
                f"{result['failed']} failed"
            )
        self._update_job(
            job_id,
            status=status,
            finished_at=self._utcnow(),
            log_summary=msg,
            progress_current=result["attempted"],
            progress_total=result["total_queued_at_start"],
        )
        invalidate_disk_usage_cache()

    def _run_processing(
        self,
        job_id: int,
        stop: threading.Event,
        timeslot_ids: Optional[list[int]],
    ) -> None:
        progress = self._make_progress(job_id)
        result = run_processing_worker(
            get_settings(),
            progress=progress,
            stop_flag=stop.is_set,
            only_ids=timeslot_ids,
        )
        status = "paused" if result.get("stopped") else "completed"
        self._update_job(
            job_id,
            status=status,
            finished_at=self._utcnow(),
            log_summary=(
                f"Processing: {result['processed_ok']} ok, {result['failed']} failed"
            ),
            progress_current=result["processed_ok"] + result["failed"],
            progress_total=result["total"],
        )
        invalidate_disk_usage_cache()


job_manager = JobManager()
