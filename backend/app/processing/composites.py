"""Standard SEVIRI composites via satpy + PNG export."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def _label(img: Image.Image, title: str) -> Image.Image:
    font, small = _fonts()
    pad = 8
    bar_h = 48
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([(0, 0), (img.width, bar_h)], fill=(8, 16, 24, 180))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)
    draw.text((pad, 6), title, fill=(220, 245, 250), font=font)
    draw.text((pad, 28), "MSG SEVIRI composite · HRIT Native", fill=(140, 180, 190), font=small)
    return img.convert("RGB")


@lru_cache(maxsize=1)
def _fonts():
    try:
        font = ImageFont.truetype("arial.ttf", 18)
        small = ImageFont.truetype("arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
        small = font
    return font, small


def render_composite_png(
    rgb_data: np.ndarray,
    composite_name: str,
    timeslot_label: str,
    out_path: Path,
    thumb_path: Path,
    satellite: str = "MSG",
    compress_level: int = 1,
) -> None:
    """
    rgb_data expected shape (y, x, 3|4) in 0–1 or 0–255.
    Alpha is dropped; north-up orientation is applied when the Scene is loaded.
    """
    arr = np.asarray(rgb_data, dtype=np.float32)
    if arr.ndim == 3 and arr.shape[0] in (3, 4):
        arr = np.moveaxis(arr, 0, -1)
    if arr.ndim == 3 and arr.shape[-1] == 4:
        arr = arr[..., :3]
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    finite_max = float(np.nanmax(arr)) if arr.size else 0.0
    finite_min = float(np.nanmin(arr)) if arr.size else 0.0
    if finite_max <= 1.01 and finite_min >= -0.05:
        arr = np.clip(arr, 0.0, 1.0) * 255.0
    elif finite_max <= 255.0 and finite_min >= -1.0 and finite_max > 32.0:
        # Already roughly display-scaled
        arr = np.clip(arr, 0.0, 255.0)
    else:
        # Enhanced RGB often lands in ~0–3 (or similar); stretch robustly
        lo = float(np.nanpercentile(arr, 1))
        hi = float(np.nanpercentile(arr, 99))
        if hi <= lo:
            hi = lo + 1.0
        arr = (arr - lo) / (hi - lo) * 255.0
    arr = np.nan_to_num(arr, nan=0.0, posinf=255.0, neginf=0.0)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr, mode="RGB")
    img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
    title = f"{satellite} · {composite_name} · {timeslot_label}"
    img = _label(img, title)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG", optimize=False, compress_level=compress_level)
    thumb = img.copy()
    thumb.thumbnail((320, 320), Image.Resampling.LANCZOS)
    thumb.save(thumb_path, format="PNG", optimize=False, compress_level=compress_level)
