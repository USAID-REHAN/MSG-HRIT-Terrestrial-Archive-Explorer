"""Final Globe Mix — list / generate / serve summary globes (one per sample timeslot)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import ActionResult, TimeslotOut
from app.config import get_settings
from app.db.models import Product, Timeslot
from app.db.session import get_db, session_scope
from app.processing.final_globe import (
    FINAL_GLOBE_PRODUCT_KIND,
    FINAL_GLOBE_PRODUCT_NAME,
    FINAL_GLOBE_SOURCE_LIMIT,
    generate_all_final_globes,
    generate_final_globe_for_timeslot,
)
from app.sampling.selector import sample_match_info

logger = logging.getLogger(__name__)
router = APIRouter(tags=["final-globes"])

_gen_lock = threading.Lock()
_gen_running = False
_gen_status: dict = {
    "running": False,
    "last_result": None,
    "error": None,
}


class FinalGlobeItem(BaseModel):
    timeslot_id: int
    date: str
    time: str
    sample_role: str | None
    sample_note: str | None = None
    status: str  # generated | missing | error
    product_id: int | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    error_message: str | None = None
    source_limit: int = FINAL_GLOBE_SOURCE_LIMIT
    generated_at: str | None = None


def _urls(timeslot_id: int, generated_at) -> tuple[str, str]:
    bust = ""
    if generated_at is not None:
        try:
            bust = f"?v={int(generated_at.timestamp())}"
        except Exception:  # noqa: BLE001
            bust = f"?v={generated_at}"
    return (
        f"/api/final-globes/{timeslot_id}/image{bust}",
        f"/api/final-globes/{timeslot_id}/thumbnail{bust}",
    )


class FinalGlobeListResponse(BaseModel):
    product_name: str
    product_label: str
    description: str
    source_limit: int
    total: int
    generated_count: int
    items: list[FinalGlobeItem]
    generate_running: bool


def _annotate(ts: Timeslot) -> dict:
    info = sample_match_info(ts.sample_role, ts.time)
    return info


@router.get("/final-globes", response_model=FinalGlobeListResponse)
def list_final_globes(db: Session = Depends(get_db)):
    slots = list(
        db.execute(
            select(Timeslot)
            .where(
                Timeslot.sample_role.is_not(None),
                Timeslot.download_status == "downloaded",
            )
            .order_by(Timeslot.date, Timeslot.time)
        )
        .scalars()
        .all()
    )
    products = {
        p.timeslot_id: p
        for p in db.execute(
            select(Product).where(Product.product_name == FINAL_GLOBE_PRODUCT_NAME)
        )
        .scalars()
        .all()
    }

    items: list[FinalGlobeItem] = []
    generated_count = 0
    for ts in slots:
        p = products.get(ts.id)
        info = _annotate(ts)
        if (
            p
            and p.availability_status == "generated"
            and p.local_image_path
            and Path(p.local_image_path).exists()
        ):
            generated_count += 1
            image_url, thumbnail_url = _urls(ts.id, p.generated_at)
            items.append(
                FinalGlobeItem(
                    timeslot_id=ts.id,
                    date=ts.date,
                    time=ts.time,
                    sample_role=ts.sample_role,
                    sample_note=info.get("sample_note"),
                    status="generated",
                    product_id=p.id,
                    image_url=image_url,
                    thumbnail_url=thumbnail_url,
                    generated_at=p.generated_at.isoformat() if p.generated_at else None,
                )
            )
        elif p and p.availability_status == "unavailable_error":
            items.append(
                FinalGlobeItem(
                    timeslot_id=ts.id,
                    date=ts.date,
                    time=ts.time,
                    sample_role=ts.sample_role,
                    sample_note=info.get("sample_note"),
                    status="error",
                    product_id=p.id,
                    error_message=p.error_message,
                )
            )
        else:
            items.append(
                FinalGlobeItem(
                    timeslot_id=ts.id,
                    date=ts.date,
                    time=ts.time,
                    sample_role=ts.sample_role,
                    sample_note=info.get("sample_note"),
                    status="missing",
                )
            )

    return FinalGlobeListResponse(
        product_name=FINAL_GLOBE_PRODUCT_NAME,
        product_label="Final Globe Mix",
        description=(
            "One whole-disk summary image per sampled timeslot. Each globe is a "
            "role-aware mix (day → natural colour, twilight → airmass, night → "
            "IR/microphysics) so daytime, twilight, and nighttime cards look distinct."
        ),
        source_limit=FINAL_GLOBE_SOURCE_LIMIT,
        total=len(items),
        generated_count=generated_count,
        items=items,
        generate_running=_gen_status["running"],
    )


@router.get("/final-globes/status")
def final_globes_status():
    return {
        "running": _gen_status["running"],
        "last_result": _gen_status["last_result"],
        "error": _gen_status["error"],
        "product_name": FINAL_GLOBE_PRODUCT_NAME,
        "product_kind": FINAL_GLOBE_PRODUCT_KIND,
        "source_limit": FINAL_GLOBE_SOURCE_LIMIT,
    }


@router.post("/final-globes/generate", response_model=ActionResult)
def generate_final_globes(force: bool = Query(False)):
    """Start background generation of Final Globe Mix for all downloaded sample timeslots."""
    global _gen_running

    with _gen_lock:
        if _gen_status["running"]:
            return ActionResult(
                ok=False,
                job_type="final_globe",
                error="Final Globe Mix generation already running",
            )
        _gen_status["running"] = True
        _gen_status["error"] = None

    def runner() -> None:
        global _gen_running
        try:
            with session_scope() as db:
                result = generate_all_final_globes(
                    db, get_settings(), force=force
                )
            _gen_status["last_result"] = result
            logger.info("Final Globe Mix batch done: %s", result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Final Globe Mix batch failed")
            _gen_status["error"] = str(exc)
            _gen_status["last_result"] = None
        finally:
            with _gen_lock:
                _gen_status["running"] = False

    threading.Thread(target=runner, name="final-globe-gen", daemon=True).start()
    return ActionResult(ok=True, job_type="final_globe")


@router.post("/final-globes/{timeslot_id}/generate", response_model=ActionResult)
def generate_one_final_globe(timeslot_id: int, force: bool = Query(False), db: Session = Depends(get_db)):
    ts = db.get(Timeslot, timeslot_id)
    if ts is None:
        raise HTTPException(404, "Timeslot not found")
    if ts.download_status != "downloaded":
        raise HTTPException(400, "Timeslot not downloaded yet")
    row = generate_final_globe_for_timeslot(db, ts, get_settings(), force=force)
    db.commit()
    return ActionResult(
        ok=row.availability_status == "generated",
        job_type="final_globe",
        error=row.error_message if row.availability_status != "generated" else None,
    )


@router.get("/final-globes/{timeslot_id}")
def get_final_globe(timeslot_id: int, db: Session = Depends(get_db)):
    ts = db.get(Timeslot, timeslot_id)
    if ts is None:
        raise HTTPException(404, "Timeslot not found")
    p = db.execute(
        select(Product).where(
            Product.timeslot_id == timeslot_id,
            Product.product_name == FINAL_GLOBE_PRODUCT_NAME,
        )
    ).scalar_one_or_none()
    info = _annotate(ts)
    ts_out = TimeslotOut.model_validate(ts)
    ts_out.sample_target_time = info.get("sample_target_time")
    ts_out.sample_match = info.get("sample_match")
    ts_out.sample_offset_minutes = info.get("sample_offset_minutes")
    ts_out.sample_note = info.get("sample_note")

    status = "missing"
    image_url = None
    thumbnail_url = None
    error_message = None
    product_id = None
    if p:
        product_id = p.id
        if (
            p.availability_status == "generated"
            and p.local_image_path
            and Path(p.local_image_path).exists()
        ):
            status = "generated"
            image_url, thumbnail_url = _urls(timeslot_id, p.generated_at)
        elif p.availability_status == "unavailable_error":
            status = "error"
            error_message = p.error_message

    return {
        "product_name": FINAL_GLOBE_PRODUCT_NAME,
        "product_label": "Final Globe Mix",
        "source_limit": FINAL_GLOBE_SOURCE_LIMIT,
        "timeslot": ts_out,
        "status": status,
        "product_id": product_id,
        "image_url": image_url,
        "thumbnail_url": thumbnail_url,
        "error_message": error_message,
    }


@router.get("/final-globes/{timeslot_id}/image")
def serve_final_globe_image(timeslot_id: int, db: Session = Depends(get_db)):
    p = db.execute(
        select(Product).where(
            Product.timeslot_id == timeslot_id,
            Product.product_name == FINAL_GLOBE_PRODUCT_NAME,
        )
    ).scalar_one_or_none()
    if p is None or not p.local_image_path or not Path(p.local_image_path).exists():
        raise HTTPException(404, "Final Globe Mix image not found — generate it first")
    return FileResponse(p.local_image_path, media_type="image/png")


@router.get("/final-globes/{timeslot_id}/thumbnail")
def serve_final_globe_thumb(timeslot_id: int, db: Session = Depends(get_db)):
    p = db.execute(
        select(Product).where(
            Product.timeslot_id == timeslot_id,
            Product.product_name == FINAL_GLOBE_PRODUCT_NAME,
        )
    ).scalar_one_or_none()
    if (
        p is None
        or not p.local_thumbnail_path
        or not Path(p.local_thumbnail_path).exists()
    ):
        raise HTTPException(404, "Final Globe Mix thumbnail not found")
    return FileResponse(p.local_thumbnail_path, media_type="image/png")
