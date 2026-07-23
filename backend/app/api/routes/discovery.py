"""Discovery + sampling endpoints."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import ActionResult, DateSummary
from app.config import get_settings
from app.db.models import Timeslot
from app.db.session import get_db
from app.jobs.manager import job_manager
from app.sampling.selector import sample_match_info

router = APIRouter(tags=["discovery"])


@router.post("/discovery/run", response_model=ActionResult)
def run_discovery():
    result = job_manager.start_discovery()
    return ActionResult(
        ok=result["ok"],
        job_id=result.get("job_id"),
        job_type=result.get("job_type"),
        error=result.get("error"),
    )


@router.get("/discovery/status")
def discovery_status(db: Session = Depends(get_db)):
    total = db.execute(select(func.count()).select_from(Timeslot)).scalar_one()
    bytes_total = db.execute(
        select(func.coalesce(func.sum(Timeslot.server_reported_size_bytes), 0))
    ).scalar_one()
    date_min = db.execute(select(func.min(Timeslot.date))).scalar_one()
    date_max = db.execute(select(func.max(Timeslot.date))).scalar_one()
    years = db.execute(select(Timeslot.year).distinct()).scalars().all()
    return {
        "discovered_total": total,
        "discovered_bytes": int(bytes_total or 0),
        "date_min": date_min,
        "date_max": date_max,
        "years": sorted(years),
        "job_running": job_manager.is_running("discovery"),
    }


@router.post("/sampling/run", response_model=ActionResult)
def run_sampling():
    result = job_manager.start_sampling()
    return ActionResult(
        ok=result["ok"],
        job_id=result.get("job_id"),
        job_type=result.get("job_type"),
        error=result.get("error"),
    )


@router.get("/sampling/status")
def sampling_status(db: Session = Depends(get_db)):
    settings = get_settings()
    selected = list(
        db.execute(select(Timeslot).where(Timeslot.sample_role.is_not(None)))
        .scalars()
        .all()
    )
    by_date: dict[str, list] = defaultdict(list)
    for ts in selected:
        by_date[ts.date].append(ts)

    per_date = []
    for date, rows in sorted(by_date.items()):
        roles = sorted({r.sample_role for r in rows if r.sample_role})
        per_date.append(
            {
                "date": date,
                "count": len(rows),
                "roles": roles,
                "bytes": sum(r.server_reported_size_bytes or 0 for r in rows),
            }
        )

    return {
        "total_selected": len(selected),
        "total_selected_bytes": sum(t.server_reported_size_bytes or 0 for t in selected),
        "per_date": per_date,
        "targets": {
            "daytime": settings.sample_daytime_target,
            "nighttime": settings.sample_nighttime_target,
            "twilight": settings.sample_twilight_target,
            "tolerance_minutes": settings.sample_tolerance_minutes,
            "nearest_fallback": settings.sample_nearest_fallback,
            "files_per_date": settings.sample_files_per_date,
            "download_everything_per_date": settings.download_everything_per_date,
        },
        "job_running": job_manager.is_running("sampling"),
    }


@router.get("/browse/dates", response_model=list[DateSummary])
def list_dates(db: Session = Depends(get_db)):
    rows = list(db.execute(select(Timeslot)).scalars().all())
    by_date: dict[str, list[Timeslot]] = defaultdict(list)
    for ts in rows:
        by_date[ts.date].append(ts)

    out: list[DateSummary] = []
    for date in sorted(by_date.keys()):
        slots = by_date[date]
        sampled = [s for s in slots if s.sample_role]
        roles = sorted({s.sample_role for s in sampled if s.sample_role})
        n = len(roles)
        nearest_n = sum(
            1
            for s in sampled
            if sample_match_info(s.sample_role, s.time).get("sample_match")
            == "nearest_fallback"
        )
        if n == 0:
            label = "0/3 sampled — no files for this date"
        elif nearest_n:
            label = f"{n}/3 sampled — {nearest_n} nearest-available (off standard time)"
        elif n < 3:
            label = f"{n}/3 sampled — partial day"
        else:
            label = "3/3 sampled"
        out.append(
            DateSummary(
                date=date,
                year=slots[0].year,
                discovered_count=len(slots),
                sampled_count=n,
                sample_roles_filled=roles,
                sample_label=label,
                total_bytes=sum(s.server_reported_size_bytes or 0 for s in slots),
                nearest_fallback_count=nearest_n,
            )
        )
    return out
