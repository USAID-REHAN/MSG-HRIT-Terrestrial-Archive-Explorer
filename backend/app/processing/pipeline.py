"""Orchestrate channel + composite processing for downloaded timeslots."""

from __future__ import annotations

import logging
import multiprocessing
import os
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable, Optional

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Product, Timeslot
from app.db.session import session_scope
from app.processing.channels import (
    array_from_dataset,
    arrays_from_datasets,
    load_channel_dataset,
    render_channel_png,
)
from app.processing.composite_catalog import COMPOSITE_NAMES, SOLAR_DEPENDENT_COMPOSITES
from app.processing.composite_loader import (
    CompositeLoadContext,
    composite_arrays_from_datasets,
    composite_array_from_dataset,
    is_nightish_composite_error,
    load_composite_dataset,
)
from app.processing.composites import render_composite_png
from app.processing.reader import (
    CHANNEL_NAMES,
    available_datasets,
    load_scene,
    resolve_dataset_name,
)
from app.reference.product_reference import SOLAR_DEPENDENT_CHANNELS

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str], None]

# IR / WV / non-solar composites should always yield PNGs for a valid MSG disk.
# Solar composites may be night-blank; everything else missing ⇒ not done.
ALWAYS_EXPECTED_CHANNELS = tuple(
    n for n in CHANNEL_NAMES if n not in SOLAR_DEPENDENT_CHANNELS
)
ALWAYS_EXPECTED_COMPOSITES = tuple(
    n for n in COMPOSITE_NAMES if n not in SOLAR_DEPENDENT_COMPOSITES
)
MIN_GENERATED_FOR_SUCCESS = len(ALWAYS_EXPECTED_CHANNELS)  # at least all IR/WV


def _upsert_product(
    db: Session,
    timeslot_id: int,
    name: str,
    kind: str,
    status: str,
    image: Optional[str] = None,
    thumb: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    row = db.execute(
        select(Product).where(Product.timeslot_id == timeslot_id, Product.product_name == name)
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if row is None:
        row = Product(
            timeslot_id=timeslot_id,
            product_name=name,
            product_kind=kind,
            availability_status=status,
            local_image_path=image,
            local_thumbnail_path=thumb,
            generated_at=now if status == "generated" else None,
            error_message=error,
        )
        db.add(row)
    else:
        row.availability_status = status
        row.local_image_path = image
        row.local_thumbnail_path = thumb
        row.generated_at = now if status == "generated" else row.generated_at
        row.error_message = error


def _write_all_products(timeslot_id: int, outcomes: list[dict]) -> None:
    """Short DB transaction: replace all product rows for a timeslot."""
    with session_scope() as db:
        db.execute(delete(Product).where(Product.timeslot_id == timeslot_id))
        db.flush()
        for o in outcomes:
            _upsert_product(
                db,
                timeslot_id,
                o["name"],
                o["kind"],
                o["status"],
                image=o.get("image"),
                thumb=o.get("thumb"),
                error=o.get("error"),
            )


def _error_outcomes(err: str) -> list[dict]:
    out: list[dict] = []
    for name in CHANNEL_NAMES:
        out.append(
            {"name": name, "kind": "channel", "status": "unavailable_error", "error": err}
        )
    for name in COMPOSITE_NAMES:
        out.append(
            {
                "name": name,
                "kind": "composite",
                "status": "unavailable_error",
                "error": err,
            }
        )
    return out


def _append_composite_error(
    outcomes: list[dict],
    name: str,
    exc: BaseException,
    available_comps: set[str],
) -> None:
    night = name in SOLAR_DEPENDENT_COMPOSITES and (
        is_nightish_composite_error(name, exc, SOLAR_DEPENDENT_COMPOSITES)
        or name not in available_comps
    )
    logger.warning("Composite %s failed: %s", name, exc)
    outcomes.append(
        {
            "name": name,
            "kind": "composite",
            "status": "unavailable_night" if night else "unavailable_error",
            "error": None if night else str(exc),
        }
    )


def _render_products(
    nat_path: Path,
    date: str,
    time: str,
    label: str,
    out_dir: Path,
    thumb_dir: Path,
    settings: Settings,
) -> tuple[list[dict], dict[str, float]]:
    """
    Run satpy + PNG export with NO open DB session.
    Holding a SQLite write lock across multi-minute satpy loads caused
    'database is locked' + failed Scene opens when Start Processing /
    CLI workers overlapped.
    """
    started = perf_counter()
    outcomes: list[dict] = []
    scn = load_scene(nat_path, date, time)
    scene_loaded = perf_counter()
    avail = available_datasets(scn)

    loaded_channels: list[tuple[str, object]] = []
    for name in CHANNEL_NAMES:
        satpy_name = resolve_dataset_name(scn, name)
        if satpy_name is None and name not in avail:
            status = (
                "unavailable_night"
                if name in SOLAR_DEPENDENT_CHANNELS
                else "unavailable_error"
            )
            err = None if status == "unavailable_night" else f"{name} not present in file"
            outcomes.append(
                {"name": name, "kind": "channel", "status": status, "error": err}
            )
            continue
        try:
            load_name = satpy_name or name
            dataset = load_channel_dataset(scn, load_name)
            loaded_channels.append((name, dataset))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Channel %s failed: %s", name, exc)
            status = (
                "unavailable_night"
                if name in SOLAR_DEPENDENT_CHANNELS
                and ("night" in str(exc).lower() or "solar" in str(exc).lower())
                else "unavailable_error"
            )
            outcomes.append(
                {
                    "name": name,
                    "kind": "channel",
                    "status": status,
                    "error": None if status == "unavailable_night" else str(exc),
                }
            )

    try:
        channel_arrays = arrays_from_datasets([dataset for _, dataset in loaded_channels])
    except Exception:  # noqa: BLE001
        logger.warning("Channel batch compute failed; falling back to isolated computes")
        channel_arrays = []
        for _, dataset in loaded_channels:
            try:
                channel_arrays.append(array_from_dataset(dataset))
            except Exception as exc:  # noqa: BLE001
                channel_arrays.append(exc)

    for (name, _dataset), data_or_error in zip(loaded_channels, channel_arrays):
        try:
            if isinstance(data_or_error, BaseException):
                raise data_or_error
            data = data_or_error
            finite = data[np_isfinite(data)]
            if name in SOLAR_DEPENDENT_CHANNELS and (
                finite.size == 0 or float(finite.max()) <= 0
            ):
                outcomes.append(
                    {"name": name, "kind": "channel", "status": "unavailable_night"}
                )
                continue
            img_path = out_dir / f"{name}.png"
            th_path = thumb_dir / f"{name}_thumb.png"
            render_channel_png(
                data,
                name,
                label,
                img_path,
                th_path,
                compress_level=settings.png_compress_level,
            )
            outcomes.append(
                {
                    "name": name,
                    "kind": "channel",
                    "status": "generated",
                    "image": str(img_path),
                    "thumb": str(th_path),
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Channel %s failed: %s", name, exc)
            status = (
                "unavailable_night"
                if name in SOLAR_DEPENDENT_CHANNELS
                and ("night" in str(exc).lower() or "solar" in str(exc).lower())
                else "unavailable_error"
            )
            outcomes.append(
                {
                    "name": name,
                    "kind": "channel",
                    "status": status,
                    "error": None if status == "unavailable_night" else str(exc),
                }
            )

    channels_finished = perf_counter()
    try:
        available_comps = set(scn.available_composite_names())
    except Exception:  # noqa: BLE001
        available_comps = set()

    context = CompositeLoadContext(scn)
    context.prepare(COMPOSITE_NAMES)
    batch_size = settings.composite_batch_size
    for offset in range(0, len(COMPOSITE_NAMES), batch_size):
        batch = COMPOSITE_NAMES[offset : offset + batch_size]
        loaded: list[tuple[str, object]] = []
        for name in batch:
            try:
                loaded.append((name, load_composite_dataset(scn, name, context)))
            except Exception as exc:  # noqa: BLE001
                _append_composite_error(outcomes, name, exc, available_comps)

        try:
            arrays = composite_arrays_from_datasets([dataset for _, dataset in loaded])
        except Exception:  # noqa: BLE001
            logger.warning(
                "Composite batch %s-%s failed; falling back to isolated computes",
                offset,
                offset + len(batch),
            )
            arrays = []
            for _, dataset in loaded:
                try:
                    arrays.append(composite_array_from_dataset(dataset))
                except Exception as exc:  # noqa: BLE001
                    arrays.append(exc)

        for (name, _dataset), data_or_error in zip(loaded, arrays):
            try:
                if isinstance(data_or_error, BaseException):
                    raise data_or_error
                img_path = out_dir / f"{name}.png"
                th_path = thumb_dir / f"{name}_thumb.png"
                render_composite_png(
                    data_or_error,
                    name,
                    label,
                    img_path,
                    th_path,
                    compress_level=settings.png_compress_level,
                )
                outcomes.append(
                    {
                        "name": name,
                        "kind": "composite",
                        "status": "generated",
                        "image": str(img_path),
                        "thumb": str(th_path),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                _append_composite_error(outcomes, name, exc, available_comps)

    finished = perf_counter()
    timings = {
        "scene_seconds": round(scene_loaded - started, 3),
        "channels_seconds": round(channels_finished - scene_loaded, 3),
        "composites_seconds": round(finished - channels_finished, 3),
        "total_seconds": round(finished - started, 3),
    }
    return outcomes, timings


def process_timeslot(timeslot_id: int, settings: Optional[Settings] = None) -> dict:
    settings = settings or get_settings()

    # --- short read: gather paths, then release DB before satpy ---
    with session_scope() as db:
        ts = db.get(Timeslot, timeslot_id)
        if ts is None:
            return {"ok": False, "error": "not found"}
        if ts.download_status != "downloaded" or not ts.local_raw_path:
            return {"ok": False, "error": "not downloaded"}
        nat_path = Path(ts.local_raw_path)
        date, time, year = ts.date, ts.time, ts.year
        label = f"{date} {time}"

    if not nat_path.exists():
        err = f"Raw file missing on disk: {nat_path}"
        _write_all_products(timeslot_id, _error_outcomes(err))
        return {"ok": False, "error": err}

    out_dir = settings.processed_dir / year / date / time
    thumb_dir = settings.thumbnails_dir / year / date / time

    try:
        outcomes, timings = _render_products(
            nat_path, date, time, label, out_dir, thumb_dir, settings
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to process Scene for %s", timeslot_id)
        _write_all_products(timeslot_id, _error_outcomes(str(exc)))
        return {"ok": False, "error": str(exc)}

    _write_all_products(timeslot_id, outcomes)

    generated = sum(1 for o in outcomes if o["status"] == "generated")
    errors = sum(1 for o in outcomes if o["status"] == "unavailable_error")
    ok = errors == 0 and generated >= MIN_GENERATED_FOR_SUCCESS
    logger.info("Processed timeslot %s in %.2fs: %s", timeslot_id, timings["total_seconds"], timings)
    return {
        "ok": ok,
        "timeslot_id": timeslot_id,
        "generated": generated,
        "errors": errors,
        "total": len(outcomes),
        "timings": timings,
    }


def np_isfinite(data):
    import numpy as np

    return np.isfinite(data)


EXPECTED_PRODUCTS = len(CHANNEL_NAMES) + len(COMPOSITE_NAMES)


def processing_stats_by_timeslot(
    db: Session, timeslot_ids: Optional[list[int]] = None
) -> dict[int, dict[str, int]]:
    query = (
        select(
            Product.timeslot_id,
            func.count(Product.id).label("total"),
            func.sum(
                case((Product.availability_status == "generated", 1), else_=0)
            ).label("generated"),
            func.sum(
                case((Product.availability_status == "unavailable_night", 1), else_=0)
            ).label("night"),
            func.sum(
                case((Product.availability_status == "unavailable_error", 1), else_=0)
            ).label("error"),
        )
        .group_by(Product.timeslot_id)
    )
    if timeslot_ids is not None:
        if not timeslot_ids:
            return {}
        query = query.where(Product.timeslot_id.in_(timeslot_ids))
    rows = db.execute(query).all()
    return {
        int(row.timeslot_id): {
            "total": int(row.total or 0),
            "generated": int(row.generated or 0),
            "night": int(row.night or 0),
            "error": int(row.error or 0),
        }
        for row in rows
    }


def timeslot_processing_stats(db: Session, timeslot_id: int) -> dict[str, int]:
    return processing_stats_by_timeslot(db, [timeslot_id]).get(
        timeslot_id, {"total": 0, "generated": 0, "night": 0, "error": 0}
    )


def is_timeslot_successfully_processed(db: Session, timeslot_id: int) -> bool:
    """
    True only when all channel+composite outcomes exist, none are hard errors,
    and enough PNG products were actually generated.

    - Night blanks for solar channels / solar composites are OK.
    - Zero generated (all error OR falsely all-night) is NOT success — those
      must stay in the Start Processing queue.
    """
    s = timeslot_processing_stats(db, timeslot_id)
    return (
        s["total"] >= EXPECTED_PRODUCTS
        and s["error"] == 0
        and s["generated"] >= MIN_GENERATED_FOR_SUCCESS
    )


def timeslots_needing_processing(db: Session) -> list[int]:
    """
    Queue any downloaded timeslot that is incomplete OR has error products
    OR produced zero / too-few images.
    """
    ids = list(
        db.execute(
            select(Timeslot.id).where(Timeslot.download_status == "downloaded")
        ).scalars()
    )
    stats = processing_stats_by_timeslot(db, ids)
    return [
        tid
        for tid in ids
        if (
            stats.get(tid, {}).get("total", 0) < EXPECTED_PRODUCTS
            or stats.get(tid, {}).get("error", 0) > 0
            or stats.get(tid, {}).get("generated", 0) < MIN_GENERATED_FOR_SUCCESS
        )
    ]


def _configure_processing_threads(threads: int) -> None:
    value = str(threads)
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[name] = value


def _process_timeslot_worker(timeslot_id: int, settings_data: dict) -> dict:
    settings = Settings.model_validate(settings_data)
    _configure_processing_threads(settings.processing_threads_per_worker)
    import dask

    with dask.config.set(
        scheduler="threads", num_workers=settings.processing_threads_per_worker
    ):
        return process_timeslot(timeslot_id, settings)


def run_processing_worker(
    settings: Optional[Settings] = None,
    progress: Optional[ProgressCallback] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
    only_ids: Optional[list[int]] = None,
) -> dict:
    settings = settings or get_settings()
    stop_flag = stop_flag or (lambda: False)

    with session_scope() as db:
        ids = only_ids if only_ids is not None else timeslots_needing_processing(db)

    total = len(ids)
    if progress:
        progress(0, total, f"Processing queue: {total}")

    ok = 0
    failed = 0
    completed = 0
    workers = min(settings.processing_workers, total) if total else 0
    _configure_processing_threads(settings.processing_threads_per_worker)

    if workers <= 1:
        for tid in ids:
            if stop_flag():
                break
            if progress:
                progress(completed, total, f"Processing timeslot {tid}")
            result = _process_timeslot_worker(tid, settings.model_dump(mode="python"))
            completed += 1
            if result.get("ok"):
                ok += 1
            else:
                failed += 1
    elif workers:
        settings_data = settings.model_dump(mode="python")
        remaining = iter(ids)
        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
            pending: dict = {}

            def submit_next() -> bool:
                if stop_flag():
                    return False
                try:
                    tid = next(remaining)
                except StopIteration:
                    return False
                future = pool.submit(_process_timeslot_worker, tid, settings_data)
                pending[future] = tid
                return True

            for _ in range(workers):
                submit_next()

            while pending:
                done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
                for future in done:
                    tid = pending.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Processing worker failed for timeslot %s", tid)
                        result = {"ok": False, "error": str(exc)}
                    completed += 1
                    if result.get("ok"):
                        ok += 1
                    else:
                        failed += 1
                    if progress:
                        elapsed = result.get("timings", {}).get("total_seconds")
                        suffix = f" in {elapsed:.1f}s" if elapsed is not None else ""
                        progress(
                            completed,
                            total,
                            f"Processed {completed}/{total} (timeslot {tid}{suffix})",
                        )
                    submit_next()

    if progress:
        progress(completed, total, f"Processing done: {ok} ok, {failed} failed")
    return {
        "processed_ok": ok,
        "failed": failed,
        "total": total,
        "stopped": stop_flag(),
    }
