"""
Final Globe Mix — one whole-disk summary image per timeslot.

Builds a role-aware blend from a small set of channel/composite PNGs so daytime,
twilight, and nighttime globes stay visually distinct (averaging dozens of
products washes everything into the same purple mush).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Product, Timeslot
from app.processing.composite_catalog import COMPOSITE_NAMES
from app.processing.reader import CHANNEL_NAMES

logger = logging.getLogger(__name__)

FINAL_GLOBE_PRODUCT_NAME = "final_globe_mix"
FINAL_GLOBE_PRODUCT_KIND = "summary"
# Keep the public “up to N” contract, but only blend a few role-matched products.
FINAL_GLOBE_SOURCE_LIMIT = 32
FINAL_GLOBE_BLEND_COUNT = 6
FINAL_GLOBE_SIZE = 1536  # square output edge

# Fallback order when sample_role is missing.
_PRIORITY: list[str] = [
    "natural_color",
    "airmass",
    "night_microphysics",
    "day_microphysics",
    "overview",
    "dust",
    "ash",
    "convection",
    "cloudtop",
    "IR_108",
    "IR_120",
    "IR_039",
    "WV_073",
    "WV_062",
    "VIS006",
    "VIS008",
    "IR_016",
    "HRV",
    "IR_087",
    "IR_097",
    "IR_134",
]

# Role-specific heroes first — these drive the look of day / twilight / night.
_ROLE_PRIORITY: dict[str, list[str]] = {
    "daytime": [
        "natural_color",
        "day_microphysics",
        "overview",
        "VIS006",
        "VIS008",
        "IR_016",
        "HRV",
        "airmass",
        "dust",
        "convection",
    ],
    "twilight": [
        "airmass",
        "natural_color",
        "dust",
        "overview",
        "day_microphysics",
        "night_microphysics",
        "IR_039",
        "IR_108",
        "ash",
        "convection",
    ],
    "nighttime": [
        "night_microphysics",
        "cloudtop",
        "IR_108",
        "IR_120",
        "IR_039",
        "airmass",
        "dust",
        "ash",
        "WV_073",
        "WV_062",
    ],
}


def _priority_list(sample_role: str | None) -> list[str]:
    if sample_role and sample_role in _ROLE_PRIORITY:
        # Role list first, then any remaining curated names, then catalog fill.
        seen = set(_ROLE_PRIORITY[sample_role])
        return _ROLE_PRIORITY[sample_role] + [n for n in _PRIORITY if n not in seen]
    return list(_PRIORITY)


def _priority_rank(name: str, sample_role: str | None = None) -> int:
    order = _priority_list(sample_role)
    try:
        return order.index(name)
    except ValueError:
        if name in CHANNEL_NAMES:
            return 1000 + CHANNEL_NAMES.index(name)
        if name in COMPOSITE_NAMES:
            return 2000 + COMPOSITE_NAMES.index(name)
        return 9000


def _label_image(img: Image.Image, title: str, subtitle: str) -> Image.Image:
    draw_base = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    bar_h = 56
    od.rectangle([(0, 0), (img.width, bar_h)], fill=(8, 16, 24, 200))
    composed = Image.alpha_composite(draw_base, overlay)
    draw = ImageDraw.Draw(composed)
    try:
        font = ImageFont.truetype("arial.ttf", 20)
        small = ImageFont.truetype("arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
        small = font
    draw.text((10, 8), title, fill=(220, 245, 250), font=font)
    draw.text((10, 32), subtitle, fill=(140, 190, 200), font=small)
    return composed.convert("RGB")


def select_source_products(
    products: list[Product],
    sample_role: str | None = None,
    *,
    limit: int = FINAL_GLOBE_BLEND_COUNT,
) -> list[Product]:
    usable = [
        p
        for p in products
        if p.availability_status == "generated"
        and p.local_image_path
        and p.product_name != FINAL_GLOBE_PRODUCT_NAME
        and Path(p.local_image_path).exists()
    ]
    usable.sort(key=lambda p: _priority_rank(p.product_name, sample_role))
    return usable[:limit]


def blend_globe_images(paths: list[Path], size: int = FINAL_GLOBE_SIZE) -> Image.Image:
    """
    Role-hero blend: the first (highest-priority) product dominates (~70%),
    with a light accent from the remaining sources so the globe stays mixed
    but still looks like day / twilight / night.
    """
    if not paths:
        raise ValueError("No source images to blend")

    stack: list[np.ndarray] = []
    for path in paths:
        try:
            img = Image.open(path).convert("RGB")
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            stack.append(np.asarray(img, dtype=np.float32))
        except OSError as exc:
            logger.warning("Skip unreadable source %s: %s", path, exc)

    if not stack:
        raise ValueError("All source images failed to load")

    arr = np.stack(stack, axis=0)  # (N, H, W, 3)
    n = arr.shape[0]
    if n == 1:
        return Image.fromarray(np.clip(arr[0], 0, 255).astype(np.uint8))

    # Hero gets most of the weight; accents share the rest with exponential decay.
    hero_w = 0.70
    accent = np.array([0.55**i for i in range(n - 1)], dtype=np.float32)
    accent = accent / accent.sum() * (1.0 - hero_w)
    weights = np.concatenate([[hero_w], accent]).astype(np.float32)
    mean = np.tensordot(weights, arr, axes=(0, 0))
    # Mild peak lift keeps bright cloud / land features from washing out.
    peak = arr.max(axis=0)
    blended = 0.88 * mean + 0.12 * peak
    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8))


def generate_final_globe_for_timeslot(
    db: Session,
    timeslot: Timeslot,
    settings: Settings | None = None,
    *,
    force: bool = False,
) -> Product:
    """
    Build/update the Final Globe Mix product for one timeslot.
    Does not modify other products.
    """
    settings = settings or get_settings()
    products = list(
        db.execute(select(Product).where(Product.timeslot_id == timeslot.id))
        .scalars()
        .all()
    )
    existing = next(
        (p for p in products if p.product_name == FINAL_GLOBE_PRODUCT_NAME),
        None,
    )
    if (
        not force
        and existing
        and existing.availability_status == "generated"
        and existing.local_image_path
        and Path(existing.local_image_path).exists()
    ):
        return existing

    role = timeslot.sample_role or "sample"
    sources = select_source_products(products, timeslot.sample_role)
    out_dir = settings.processed_dir / timeslot.year / timeslot.date / timeslot.time
    thumb_dir = settings.thumbnails_dir / timeslot.year / timeslot.date / timeslot.time
    out_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{FINAL_GLOBE_PRODUCT_NAME}.png"
    thumb_path = thumb_dir / f"{FINAL_GLOBE_PRODUCT_NAME}_thumb.png"

    if len(sources) < 1:
        err = (
            f"Need at least 1 generated product to build Final Globe Mix "
            f"(found {len(sources)})"
        )
        if existing is None:
            existing = Product(
                timeslot_id=timeslot.id,
                product_name=FINAL_GLOBE_PRODUCT_NAME,
                product_kind=FINAL_GLOBE_PRODUCT_KIND,
                availability_status="unavailable_error",
                local_image_path=None,
                local_thumbnail_path=None,
                generated_at=None,
                error_message=err,
            )
            db.add(existing)
        else:
            existing.availability_status = "unavailable_error"
            existing.error_message = err
            existing.local_image_path = None
            existing.local_thumbnail_path = None
        db.flush()
        return existing

    title = (
        f"Final Globe Mix · {timeslot.date} {timeslot.time.replace('-', ':')} UTC"
    )
    hero = sources[0].product_name if sources else "—"
    subtitle = (
        f"{role} · hero {hero} · mix of {len(sources)} products · MSG SEVIRI"
    )

    try:
        globe = blend_globe_images([Path(p.local_image_path) for p in sources])  # type: ignore[arg-type]
        globe = _label_image(globe, title, subtitle)
        globe.save(out_path, format="PNG", optimize=True)
        thumb = globe.copy()
        thumb.thumbnail((480, 480), Image.Resampling.LANCZOS)
        thumb.save(thumb_path, format="PNG", optimize=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Final globe failed for timeslot %s", timeslot.id)
        if existing is None:
            existing = Product(
                timeslot_id=timeslot.id,
                product_name=FINAL_GLOBE_PRODUCT_NAME,
                product_kind=FINAL_GLOBE_PRODUCT_KIND,
                availability_status="unavailable_error",
                error_message=str(exc),
            )
            db.add(existing)
        else:
            existing.availability_status = "unavailable_error"
            existing.error_message = str(exc)
        db.flush()
        return existing

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    source_names = ", ".join(p.product_name for p in sources[:8])
    if len(sources) > 8:
        source_names += f", +{len(sources) - 8} more"

    if existing is None:
        existing = Product(
            timeslot_id=timeslot.id,
            product_name=FINAL_GLOBE_PRODUCT_NAME,
            product_kind=FINAL_GLOBE_PRODUCT_KIND,
            availability_status="generated",
            local_image_path=str(out_path),
            local_thumbnail_path=str(thumb_path),
            generated_at=now,
            error_message=None,
        )
        db.add(existing)
    else:
        existing.product_kind = FINAL_GLOBE_PRODUCT_KIND
        existing.availability_status = "generated"
        existing.local_image_path = str(out_path)
        existing.local_thumbnail_path = str(thumb_path)
        existing.generated_at = now
        existing.error_message = None
    db.flush()
    logger.info(
        "Final Globe Mix ready timeslot=%s sources=%s (%s)",
        timeslot.id,
        len(sources),
        source_names,
    )
    return existing


def generate_all_final_globes(
    db: Session,
    settings: Settings | None = None,
    *,
    force: bool = False,
    only_ids: Optional[list[int]] = None,
) -> dict:
    settings = settings or get_settings()
    q = select(Timeslot).where(
        Timeslot.download_status == "downloaded",
        Timeslot.sample_role.is_not(None),
    )
    if only_ids:
        q = q.where(Timeslot.id.in_(only_ids))
    slots = list(db.execute(q.order_by(Timeslot.date, Timeslot.time)).scalars().all())

    ok = 0
    failed = 0
    skipped = 0
    for ts in slots:
        before = db.execute(
            select(Product).where(
                Product.timeslot_id == ts.id,
                Product.product_name == FINAL_GLOBE_PRODUCT_NAME,
                Product.availability_status == "generated",
            )
        ).scalar_one_or_none()
        if before and before.local_image_path and Path(before.local_image_path).exists() and not force:
            skipped += 1
            continue
        row = generate_final_globe_for_timeslot(db, ts, settings, force=force)
        if row.availability_status == "generated":
            ok += 1
        else:
            failed += 1
    db.commit()
    return {
        "total_timeslots": len(slots),
        "generated": ok,
        "failed": failed,
        "skipped_existing": skipped,
        "source_limit": FINAL_GLOBE_SOURCE_LIMIT,
        "product_name": FINAL_GLOBE_PRODUCT_NAME,
    }
