"""
Queue-driven, resumable .nat downloader (BUILDPLAN §10 Step 3 / §13).
"""

from __future__ import annotations

import logging
import shutil
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Timeslot
from app.db.session import session_scope

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str], None]


class DiskSpacePaused(Exception):
    """Raised when free disk space would fall below the configured minimum."""


def free_disk_gb(path: Path) -> float:
    path.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(str(path))
    return usage.free / (1024**3)


def ensure_disk_space(settings: Settings, needed_bytes: int = 0) -> None:
    free = free_disk_gb(settings.data_root)
    needed_gb = needed_bytes / (1024**3)
    if free - needed_gb < settings.min_free_disk_gb:
        raise DiskSpacePaused(
            f"Free disk {free:.2f} GB would drop below minimum "
            f"{settings.min_free_disk_gb} GB (need ~{needed_gb:.2f} GB more)"
        )


def _download_one(
    timeslot_id: int,
    settings: Settings,
    stop_flag: Callable[[], bool],
) -> tuple[int, str, Optional[str]]:
    """
    Download a single timeslot. Returns (id, status, error_or_None).
    Uses its own DB session for thread safety.
    """
    if stop_flag():
        return timeslot_id, "paused", "Stopped by user"

    with session_scope() as db:
        ts = db.get(Timeslot, timeslot_id)
        if ts is None:
            return timeslot_id, "failed", "Timeslot not found"
        if ts.download_status == "downloaded" and ts.local_raw_path:
            local = Path(ts.local_raw_path)
            if local.exists() and (
                ts.server_reported_size_bytes is None
                or local.stat().st_size == ts.server_reported_size_bytes
            ):
                return timeslot_id, "downloaded", None

        dest = settings.raw_dir / ts.year / ts.date / ts.time / "msg15.nat"
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = urljoin(settings.archive_url, ts.server_relative_path)

        try:
            ensure_disk_space(settings, ts.server_reported_size_bytes or 0)
        except DiskSpacePaused as exc:
            ts.download_status = "queued"
            ts.last_error = str(exc)
            return timeslot_id, "paused_disk", str(exc)

        ts.download_status = "downloading"
        ts.last_error = None
        db.commit()

        tmp = dest.with_suffix(".nat.partial")
        try:
            with httpx.stream("GET", url, timeout=600.0, follow_redirects=True) as resp:
                resp.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_bytes(
                        chunk_size=settings.download_chunk_mb * 1024 * 1024
                    ):
                        if stop_flag():
                            f.close()
                            if tmp.exists():
                                tmp.unlink(missing_ok=True)
                            ts.download_status = "queued"
                            ts.last_error = "Interrupted — will resume"
                            return timeslot_id, "paused", "Interrupted"
                        f.write(chunk)

            actual = tmp.stat().st_size
            expected = ts.server_reported_size_bytes
            if expected is not None and actual != expected:
                tmp.unlink(missing_ok=True)
                ts.download_status = "failed"
                ts.last_error = (
                    f"Size mismatch: local {actual} bytes vs server-reported {expected}"
                )
                return timeslot_id, "failed", ts.last_error

            tmp.replace(dest)
            ts.local_raw_path = str(dest)
            ts.download_status = "downloaded"
            ts.downloaded_at = datetime.now(timezone.utc).replace(tzinfo=None)
            ts.last_error = None
            return timeslot_id, "downloaded", None
        except Exception as exc:  # noqa: BLE001
            logger.exception("Download failed for timeslot %s", timeslot_id)
            tmp.unlink(missing_ok=True)
            ts.download_status = "failed"
            ts.last_error = str(exc)
            return timeslot_id, "failed", str(exc)


def run_download_worker(
    settings: Optional[Settings] = None,
    progress: Optional[ProgressCallback] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
) -> dict:
    settings = settings or get_settings()
    stop_flag = stop_flag or (lambda: False)

    with session_scope() as db:
        queued = list(
            db.execute(
                select(Timeslot)
                .where(
                    Timeslot.sample_role.is_not(None),
                    Timeslot.download_status.in_(["queued", "failed", "downloading"]),
                )
                .order_by(Timeslot.date, Timeslot.time)
            )
            .scalars()
            .all()
        )
        # Reset stuck 'downloading' to queued for resume
        for ts in queued:
            if ts.download_status == "downloading":
                ts.download_status = "queued"
        ids = [ts.id for ts in queued]
        total = len(ids)

    if progress:
        progress(0, total, f"Download queue: {total} file(s)")

    done = 0
    failed = 0
    paused_disk = False
    summary_msgs: list[str] = []

    # Keep the pool full while rate-limiting actual starts, not queue construction.
    with ThreadPoolExecutor(max_workers=settings.max_concurrent_downloads) as pool:
        remaining = iter(ids)
        pending: dict = {}
        exhausted = False
        next_start = time.monotonic()

        while pending or not exhausted:
            while (
                len(pending) < settings.max_concurrent_downloads
                and not exhausted
                and not stop_flag()
                and not paused_disk
            ):
                try:
                    ts_id = next(remaining)
                except StopIteration:
                    exhausted = True
                    break
                delay = next_start - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                future = pool.submit(_download_one, ts_id, settings, stop_flag)
                pending[future] = ts_id
                next_start = time.monotonic() + settings.min_request_delay_seconds

            if not pending:
                break

            finished, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in finished:
                pending.pop(future)
                _ts_id, status, err = future.result()
                done += 1
                if status == "failed":
                    failed += 1
                if status == "paused_disk":
                    paused_disk = True
                    summary_msgs.append(err or "Disk space pause")
                if progress:
                    progress(
                        done,
                        total,
                        f"Downloaded batch progress {done}/{total} (last={status})",
                    )

    result = {
        "attempted": done,
        "failed": failed,
        "total_queued_at_start": total,
        "paused_for_disk": paused_disk,
        "stopped_by_user": stop_flag(),
        "messages": summary_msgs,
    }
    return result
