"""Download / processing / jobs / retry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import ActionResult, JobOut
from app.db.models import Job, Timeslot
from app.db.session import get_db
from app.jobs.manager import job_manager

router = APIRouter(tags=["jobs"])


@router.post("/pipeline/start", response_model=ActionResult)
def pipeline_start():
    """One-click discover → sample → download → process (does not remove step buttons)."""
    result = job_manager.start_pipeline()
    return ActionResult(
        ok=result["ok"],
        job_id=result.get("job_id"),
        job_type=result.get("job_type"),
        error=result.get("error"),
    )


@router.post("/pipeline/pause", response_model=ActionResult)
def pipeline_pause():
    ok = job_manager.request_pause("pipeline")
    return ActionResult(
        ok=ok,
        job_type="pipeline",
        error=None if ok else "No pipeline job running",
    )


@router.get("/pipeline/status")
def pipeline_status():
    return {
        "job_running": job_manager.is_running("pipeline"),
        "phases_running": {
            phase: job_manager.is_running(phase)
            for phase in ("discovery", "sampling", "download", "processing")
        },
    }


@router.post("/download/start", response_model=ActionResult)
def download_start():
    result = job_manager.start_download()
    return ActionResult(
        ok=result["ok"],
        job_id=result.get("job_id"),
        job_type=result.get("job_type"),
        error=result.get("error"),
    )


@router.post("/download/pause", response_model=ActionResult)
def download_pause():
    ok = job_manager.request_pause("download")
    return ActionResult(ok=ok, job_type="download", error=None if ok else "No download job running")


@router.get("/download/status")
def download_status(db: Session = Depends(get_db)):
    def count(status: str) -> int:
        return db.execute(
            select(func.count())
            .select_from(Timeslot)
            .where(Timeslot.sample_role.is_not(None), Timeslot.download_status == status)
        ).scalar_one()

    selected = db.execute(
        select(Timeslot).where(Timeslot.sample_role.is_not(None))
    ).scalars().all()
    selected_bytes = sum(t.server_reported_size_bytes or 0 for t in selected)
    downloaded = [t for t in selected if t.download_status == "downloaded"]
    downloaded_bytes = sum(t.server_reported_size_bytes or 0 for t in downloaded)

    return {
        "queued": count("queued"),
        "downloading": count("downloading"),
        "downloaded": count("downloaded"),
        "failed": count("failed"),
        "selected_total": len(selected),
        "selected_bytes": selected_bytes,
        "downloaded_bytes": downloaded_bytes,
        "job_running": job_manager.is_running("download"),
    }


@router.post("/processing/start", response_model=ActionResult)
def processing_start():
    result = job_manager.start_processing()
    return ActionResult(
        ok=result["ok"],
        job_id=result.get("job_id"),
        job_type=result.get("job_type"),
        error=result.get("error"),
    )


@router.post("/processing/pause", response_model=ActionResult)
def processing_pause():
    ok = job_manager.request_pause("processing")
    return ActionResult(
        ok=ok, job_type="processing", error=None if ok else "No processing job running"
    )


@router.get("/processing/status")
def processing_status(db: Session = Depends(get_db)):
    from app.processing.pipeline import (
        EXPECTED_PRODUCTS,
        MIN_GENERATED_FOR_SUCCESS,
        processing_stats_by_timeslot,
    )

    downloaded = list(
        db.execute(select(Timeslot).where(Timeslot.download_status == "downloaded"))
        .scalars()
        .all()
    )
    complete = 0
    partial = 0
    pending = 0
    failed = 0
    stats_by_id = processing_stats_by_timeslot(db, [ts.id for ts in downloaded])
    for ts in downloaded:
        stats = stats_by_id.get(
            ts.id, {"total": 0, "generated": 0, "night": 0, "error": 0}
        )
        if (
            stats["total"] >= EXPECTED_PRODUCTS
            and stats["error"] == 0
            and stats["generated"] >= MIN_GENERATED_FOR_SUCCESS
        ):
            complete += 1
        elif stats["total"] == 0:
            pending += 1
        elif stats["error"] > 0:
            failed += 1
        else:
            partial += 1
    return {
        "downloaded_timeslots": len(downloaded),
        "fully_processed": complete,
        "partial": partial,
        "pending": pending,
        "failed": failed,
        "expected_products_per_timeslot": EXPECTED_PRODUCTS,
        "job_running": job_manager.is_running("processing"),
    }


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(limit: int = 50, db: Session = Depends(get_db)):
    rows = (
        db.execute(select(Job).order_by(Job.id.desc()).limit(limit)).scalars().all()
    )
    return rows


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/timeslots/{timeslot_id}/retry-download", response_model=ActionResult)
def retry_download(timeslot_id: int):
    result = job_manager.retry_download(timeslot_id)
    return ActionResult(
        ok=result.get("ok", True),
        job_id=result.get("job_id"),
        job_type=result.get("job_type"),
        error=result.get("error"),
    )


@router.post("/timeslots/{timeslot_id}/retry-processing", response_model=ActionResult)
def retry_processing(timeslot_id: int):
    result = job_manager.retry_processing(timeslot_id)
    return ActionResult(
        ok=result.get("ok", True),
        job_id=result.get("job_id"),
        job_type=result.get("job_type"),
        error=result.get("error"),
    )
