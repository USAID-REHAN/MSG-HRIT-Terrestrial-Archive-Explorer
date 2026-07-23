"""Per-channel PNG rendering with labels and thumbnails."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Colormap hints by channel family
SOLAR = {"HRV", "VIS006", "VIS008", "IR_016"}
WATER_VAPOUR = {"WV_062", "WV_073"}
IR_WINDOW = {"IR_039", "IR_087", "IR_097", "IR_108", "IR_120", "IR_134"}


def _to_uint8(data: np.ndarray, invert: bool = False) -> np.ndarray:
    arr = np.asarray(data, dtype=np.float32)
    mask = np.isfinite(arr)
    if not mask.any():
        return np.zeros(arr.shape, dtype=np.uint8)
    lo = np.nanpercentile(arr[mask], 2)
    hi = np.nanpercentile(arr[mask], 98)
    if hi <= lo:
        hi = lo + 1.0
    norm = np.clip((arr - lo) / (hi - lo), 0, 1)
    if invert:
        norm = 1.0 - norm
    norm = np.nan_to_num(norm, nan=0.0, posinf=1.0, neginf=0.0)
    out = (norm * 255).astype(np.uint8)
    out[~mask] = 0
    return out


def _apply_tint(gray: np.ndarray, channel: str) -> np.ndarray:
    """Return RGB uint8 array."""
    g = gray.astype(np.float32) / 255.0
    if channel in SOLAR:
        # warm daylight tint
        r = np.clip(g * 1.05, 0, 1)
        green = g
        b = np.clip(g * 0.9, 0, 1)
    elif channel in WATER_VAPOUR:
        # teal WV look
        r = g * 0.35
        green = g * 0.85
        b = np.clip(g * 1.1, 0, 1)
    else:
        # IR: inverted cold=bright already handled; cool slate
        r = g * 0.85
        green = g * 0.9
        b = np.clip(g * 1.05, 0, 1)
    rgb = np.stack([r, green, b], axis=-1)
    return (rgb * 255).astype(np.uint8)


def _label_image(img: Image.Image, title: str) -> Image.Image:
    font, small = _fonts()
    pad = 8
    # Dark translucent bar
    bar_h = 48
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([(0, 0), (img.width, bar_h)], fill=(8, 16, 24, 180))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)
    draw.text((pad, 6), title, fill=(220, 245, 250), font=font)
    draw.text((pad, 28), "MSG SEVIRI · HRIT Native", fill=(140, 180, 190), font=small)
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


def render_channel_png(
    data: np.ndarray,
    channel: str,
    timeslot_label: str,
    out_path: Path,
    thumb_path: Path,
    satellite: str = "MSG",
    compress_level: int = 1,
) -> None:
    invert = channel in IR_WINDOW or channel in WATER_VAPOUR
    gray = _to_uint8(data, invert=invert)
    rgb = _apply_tint(gray, channel)
    img = Image.fromarray(rgb, mode="RGB")
    # Cap side length so the web UI can load labeled views (native HRV is >5k px)
    img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
    title = f"{satellite} · {channel} · {timeslot_label}"
    img = _label_image(img, title)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG", optimize=False, compress_level=compress_level)
    thumb = img.copy()
    thumb.thumbnail((320, 320), Image.Resampling.LANCZOS)
    thumb.save(thumb_path, format="PNG", optimize=False, compress_level=compress_level)


def array_from_dataset(dataset) -> np.ndarray:
    vals = dataset.values
    if hasattr(vals, "compute"):
        vals = vals.compute()
    return np.asarray(vals)


def arrays_from_datasets(datasets: list) -> list[np.ndarray]:
    """Compute multiple lazy channels together so shared file reads are reused."""
    values = [dataset.data for dataset in datasets]
    try:
        import dask

        computed = dask.compute(*values)
    except ImportError:
        computed = tuple(v.compute() if hasattr(v, "compute") else v for v in values)
    return [np.asarray(value) for value in computed]


def load_channel_dataset(scn, satpy_name: str):
    """Load a channel with north-up (Russia→Antarctica top→bottom) orientation."""
    from app.processing.composite_loader import NORTH_UP_CORNER

    scn.load([satpy_name], upper_right_corner=NORTH_UP_CORNER)
    return scn[satpy_name]
