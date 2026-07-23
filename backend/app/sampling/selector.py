"""
Per-date sample selection — 3 roles near daytime/twilight/night targets
(BUILDPLAN §5 / §10 Step 2), with a nearest-slot failsafe for sparse days.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Timeslot

ProgressCallback = Callable[[int, int, str], None]

ROLE_DAYTIME = "daytime"
ROLE_NIGHTTIME = "nighttime"
ROLE_TWILIGHT = "twilight"

ROLES = (ROLE_DAYTIME, ROLE_NIGHTTIME, ROLE_TWILIGHT)


def time_to_minutes(hh_mm: str) -> int:
    """Convert 'HH-MM' or 'HH:MM' to minutes since midnight."""
    parts = hh_mm.replace(":", "-").split("-")
    return int(parts[0]) * 60 + int(parts[1])


def closest_within_tolerance(
    candidates: list[Timeslot],
    target_hh_mm: str,
    tolerance_minutes: int,
) -> Optional[Timeslot]:
    """Nearest timeslot whose clock time is within tolerance of the target."""
    target = time_to_minutes(target_hh_mm)
    best: Optional[Timeslot] = None
    best_delta: Optional[int] = None
    for ts in candidates:
        delta = abs(time_to_minutes(ts.time) - target)
        if delta <= tolerance_minutes and (best_delta is None or delta < best_delta):
            best = ts
            best_delta = delta
    return best


def closest_any(
    candidates: list[Timeslot],
    target_hh_mm: str,
) -> Optional[Timeslot]:
    """Nearest timeslot to the target with no tolerance cap (sparse-day failsafe)."""
    if not candidates:
        return None
    target = time_to_minutes(target_hh_mm)
    best = candidates[0]
    best_delta = abs(time_to_minutes(best.time) - target)
    for ts in candidates[1:]:
        delta = abs(time_to_minutes(ts.time) - target)
        if delta < best_delta:
            best = ts
            best_delta = delta
    return best


def _minutes_to_nearest(candidates: list[Timeslot], target_hh_mm: str) -> int:
    """Distance in minutes from target to the nearest candidate (or a large sentinel)."""
    pick = closest_any(candidates, target_hh_mm)
    if pick is None:
        return 24 * 60
    return abs(time_to_minutes(pick.time) - time_to_minutes(target_hh_mm))


def format_hhmm_display(hh_mm: str) -> str:
    """Server folder 'HH-MM' → display 'HH:MM'."""
    return hh_mm.replace("-", ":")


def role_target_time(role: str, settings: Optional[Settings] = None) -> Optional[str]:
    settings = settings or get_settings()
    return {
        ROLE_DAYTIME: settings.sample_daytime_target,
        ROLE_NIGHTTIME: settings.sample_nighttime_target,
        ROLE_TWILIGHT: settings.sample_twilight_target,
    }.get(role)


def sample_match_info(
    sample_role: Optional[str],
    actual_time: str,
    settings: Optional[Settings] = None,
) -> dict:
    """
    Describe whether a sampled timeslot hit the standard target window or was
    filled by the nearest-file failsafe (for UI copy on Browse / Timeslot).
    """
    settings = settings or get_settings()
    if not sample_role:
        return {
            "sample_target_time": None,
            "sample_match": None,
            "sample_offset_minutes": None,
            "sample_note": None,
        }

    target = role_target_time(sample_role, settings)
    if not target:
        return {
            "sample_target_time": None,
            "sample_match": None,
            "sample_offset_minutes": None,
            "sample_note": None,
        }

    offset = abs(time_to_minutes(actual_time) - time_to_minutes(target))
    within = offset <= settings.sample_tolerance_minutes
    match = "within_tolerance" if within else "nearest_fallback"
    actual_disp = format_hhmm_display(actual_time)
    target_disp = format_hhmm_display(target)
    tol = settings.sample_tolerance_minutes

    if within:
        note = (
            f"Exact archive time {actual_disp} — within ±{tol} min of the "
            f"standard {sample_role} target ({target_disp})."
        )
    else:
        note = (
            f"Exact archive time {actual_disp} — nearest available for "
            f"{sample_role}. Valid data, but not near the standard {sample_role} "
            f"target ({target_disp} ±{tol} min); this date had no file in that window."
        )

    return {
        "sample_target_time": target,
        "sample_match": match,
        "sample_offset_minutes": offset,
        "sample_note": note,
    }


def _assign_role(
    pick: Timeslot,
    role: str,
    eligible: list[Timeslot],
    already_have: set[str],
) -> list[Timeslot]:
    pick.sample_role = role
    pick.download_status = "queued"
    pick.last_error = None
    already_have.add(role)
    return [t for t in eligible if t.id != pick.id]


def apply_sample_selection(
    db: Session,
    settings: Optional[Settings] = None,
    progress: Optional[ProgressCallback] = None,
) -> dict:
    """
    For each distinct date, assign closest daytime/nighttime/twilight roles.

    Pass 1 — prefer timeslots within the configured tolerance of each target.
    Pass 2 — if a role is still empty and the date has leftover files, assign
    the nearest remaining timeslot (no tolerance). That keeps sparse/partial
    days from staying empty when *some* data exists.

    Never changes sample_role on timeslots that already have one.
    Only newly discovered (role-less) timeslots can be newly queued.
    """
    settings = settings or get_settings()
    targets = {
        ROLE_DAYTIME: settings.sample_daytime_target,
        ROLE_NIGHTTIME: settings.sample_nighttime_target,
        ROLE_TWILIGHT: settings.sample_twilight_target,
    }
    tolerance = settings.sample_tolerance_minutes
    nearest_fallback = settings.sample_nearest_fallback

    all_rows = list(db.execute(select(Timeslot)).scalars().all())
    by_date: dict[str, list[Timeslot]] = defaultdict(list)
    for ts in all_rows:
        by_date[ts.date].append(ts)

    dates = sorted(by_date.keys())
    newly_queued = 0
    roles_skipped = 0
    roles_via_fallback = 0
    dates_with_any = 0

    for i, date in enumerate(dates):
        slots = by_date[date]
        if progress:
            progress(i, len(dates), f"Selecting sample for {date}")

        if settings.download_everything_per_date:
            for ts in slots:
                if ts.sample_role is None:
                    ts.sample_role = ROLE_DAYTIME
                if ts.download_status == "discovered":
                    ts.download_status = "queued"
                    ts.last_error = None
                    newly_queued += 1
            if slots:
                dates_with_any += 1
            continue

        already_have = {ts.sample_role for ts in slots if ts.sample_role}
        eligible = [
            ts
            for ts in slots
            if ts.sample_role is None and ts.download_status == "discovered"
        ]

        date_assigned = 0

        # Pass 1: strict tolerance matches
        for role in ROLES:
            if role in already_have:
                continue
            pick = closest_within_tolerance(eligible, targets[role], tolerance)
            if pick is None:
                continue
            eligible = _assign_role(pick, role, eligible, already_have)
            newly_queued += 1
            date_assigned += 1

        # Pass 2: nearest remaining file for any still-empty role
        if nearest_fallback:
            unfilled = [r for r in ROLES if r not in already_have]
            # Fill the role whose target is closest to some remaining slot first,
            # so the "best" nearest match wins before leftovers go to farther roles.
            unfilled.sort(key=lambda r: _minutes_to_nearest(eligible, targets[r]))
            for role in unfilled:
                if not eligible:
                    break
                pick = closest_any(eligible, targets[role])
                if pick is None:
                    continue
                eligible = _assign_role(pick, role, eligible, already_have)
                newly_queued += 1
                date_assigned += 1
                roles_via_fallback += 1

        for role in ROLES:
            if role not in already_have:
                roles_skipped += 1

        if already_have or date_assigned:
            dates_with_any += 1

    db.commit()

    selected = list(
        db.execute(select(Timeslot).where(Timeslot.sample_role.is_not(None)))
        .scalars()
        .all()
    )
    total_bytes = sum(t.server_reported_size_bytes or 0 for t in selected)

    summary = {
        "dates_considered": len(dates),
        "dates_with_selection": dates_with_any,
        "newly_queued": newly_queued,
        "roles_filled_by_nearest_fallback": roles_via_fallback,
        "roles_skipped_no_match": roles_skipped,
        "total_selected": len(selected),
        "total_selected_bytes": total_bytes,
        "targets": targets,
        "tolerance_minutes": tolerance,
        "nearest_fallback": nearest_fallback,
        "files_per_date_policy": settings.sample_files_per_date,
        "download_everything": settings.download_everything_per_date,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }

    if progress:
        progress(len(dates), len(dates), f"Sample selection done: {len(selected)} selected")
    return summary
