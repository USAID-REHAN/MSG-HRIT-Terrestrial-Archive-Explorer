"""Mercator map-layer overlays for Pakistan-focused Dynamic Image (EUMETView-style).

Resamples MSG SEVIRI datasets from geostationary IODC into Web Mercator
(EPSG:3857) over a large rectangular ROI centred on Pakistan but spanning
neighbouring countries — suitable for Leaflet ImageOverlay stacking with
per-layer opacity / visibility.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image
from pyresample import create_area_def

from app.processing.channels import IR_WINDOW, SOLAR, WATER_VAPOUR, _apply_tint, _to_uint8

logger = logging.getLogger(__name__)

# Satpy Scene load + Mercator resample is memory-heavy. Parallel ensures for
# "Add all layers" previously crashed the backend (socket hang-ups / 500s) and
# blocked navigation. Serialize generation; callers still get a fast path when
# the overlay PNG already exists.
_MAP_OVERLAY_LOCK = threading.Lock()

# Large rectangular ROI: Pakistan in focus, neighbours included
# (Iran, Afghanistan, India, Arabian Sea / Gulf rim, Central Asia fringe)
MAP_WEST = 55.0
MAP_SOUTH = 12.0
MAP_EAST = 88.0
MAP_NORTH = 40.0
MAP_CENTER_LAT = 30.0
MAP_CENTER_LON = 69.5
MAP_DEFAULT_ZOOM = 5

# Pixel size of stored map overlay PNGs
MAP_WIDTH = 1280
MAP_HEIGHT = 1024


def map_bounds_wgs84() -> dict[str, float]:
    """Bounds for Leaflet LatLngBounds: [[south, west], [north, east]]."""
    return {
        "west": MAP_WEST,
        "south": MAP_SOUTH,
        "east": MAP_EAST,
        "north": MAP_NORTH,
        "center_lat": MAP_CENTER_LAT,
        "center_lon": MAP_CENTER_LON,
        "default_zoom": MAP_DEFAULT_ZOOM,
        "crs": "EPSG:3857",
        "projection": "Web Mercator",
    }


def map_leaflet_bounds() -> list[list[float]]:
    return [[MAP_SOUTH, MAP_WEST], [MAP_NORTH, MAP_EAST]]


def pakistan_mercator_area():
    """Web Mercator AreaDefinition covering the Pakistan-focused rectangle."""
    return create_area_def(
        "pakistan_focus_webmerc",
        3857,
        width=MAP_WIDTH,
        height=MAP_HEIGHT,
        area_extent=(MAP_WEST, MAP_SOUTH, MAP_EAST, MAP_NORTH),
        units="degrees",
        description="Pakistan-focused Web Mercator ROI for MSG Dynamic Image",
    )


def map_path_for_image(local_image_path: str | Path) -> Path:
    """Convention: gallery `VIS006.png` → map overlay `VIS006_map.png` beside it."""
    p = Path(local_image_path)
    return p.with_name(f"{p.stem}_map{p.suffix}")


def _finite_mask(arr: np.ndarray) -> np.ndarray:
    return np.isfinite(arr)


def _rgb_to_rgba(rgb: np.ndarray, alpha_mask: np.ndarray) -> np.ndarray:
    """rgb (H,W,3) uint8 + boolean mask → RGBA uint8 (transparent where False)."""
    a = np.where(alpha_mask, 255, 0).astype(np.uint8)
    return np.dstack([rgb, a])


def _channel_rgb_alpha(data: np.ndarray, channel: str) -> np.ndarray:
    invert = channel in IR_WINDOW or channel in WATER_VAPOUR
    gray = _to_uint8(data, invert=invert)
    rgb = _apply_tint(gray, channel)
    mask = _finite_mask(np.asarray(data, dtype=np.float64)) & (gray > 0)
    # Keep near-zero valid ocean/land signal for IR where gray can be low:
    if channel not in SOLAR:
        mask = _finite_mask(np.asarray(data, dtype=np.float64))
    return _rgb_to_rgba(rgb, mask)


def _composite_rgb_alpha(rgb_data: np.ndarray) -> np.ndarray:
    arr = np.asarray(rgb_data, dtype=np.float64)
    if arr.ndim == 3 and arr.shape[0] in (3, 4) and arr.shape[0] < min(arr.shape[1:]):
        arr = np.moveaxis(arr, 0, -1)
    if arr.ndim == 3 and arr.shape[-1] == 4:
        arr = arr[..., :3]
    finite = np.isfinite(arr).all(axis=-1) if arr.ndim == 3 else np.isfinite(arr)
    finite_max = float(np.nanmax(arr)) if arr.size else 0.0
    finite_min = float(np.nanmin(arr)) if arr.size else 0.0
    if finite_max <= 1.01 and finite_min >= -0.05:
        arr = np.clip(arr, 0.0, 1.0) * 255.0
    elif not (finite_max <= 255.0 and finite_min >= -1.0 and finite_max > 32.0):
        lo = float(np.nanpercentile(arr, 1))
        hi = float(np.nanpercentile(arr, 99))
        if hi <= lo:
            hi = lo + 1.0
        arr = (arr - lo) / (hi - lo) * 255.0
    arr = np.nan_to_num(arr, nan=0.0, posinf=255.0, neginf=0.0)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    bright = arr.astype(np.float32).sum(axis=-1)
    mask = finite & (bright > 8)
    return _rgb_to_rgba(arr, mask)


def _save_rgba(rgba: np.ndarray, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(out_path, format="PNG", optimize=True)


def _resample_scene_dataset(scn: Any, dataset_name: str, area=None):
    """Resample one loaded Scene dataset into the Pakistan Mercator area."""
    area = area or pakistan_mercator_area()
    if dataset_name not in scn:
        # Channel/composite must already be north-up loaded on the Scene.
        from app.processing.composite_loader import NORTH_UP_CORNER

        scn.load([dataset_name], upper_right_corner=NORTH_UP_CORNER)
    try:
        local_scn = scn.resample(
            area, datasets=[dataset_name], resampler="bilinear"
        )
    except Exception:
        logger.info("Bilinear Scene.resample failed; falling back to nearest")
        local_scn = scn.resample(
            area, datasets=[dataset_name], resampler="nearest"
        )
    return local_scn[dataset_name]


def _values(dataset) -> np.ndarray:
    vals = dataset.values
    if hasattr(vals, "compute"):
        vals = vals.compute()
    return np.asarray(vals)


def render_map_channel(
    scn: Any,
    dataset_name: str,
    channel: str,
    out_path: Path,
) -> Path:
    """Resample a single SEVIRI channel to Pakistan Mercator RGBA PNG."""
    local = _resample_scene_dataset(scn, dataset_name)
    data = _values(local)
    # If resample yields (band,y,x) somehow, take first
    if data.ndim == 3 and data.shape[0] <= 4 and data.shape[0] < min(data.shape[1:]):
        data = data[0]
    rgba = _channel_rgb_alpha(data, channel)
    _save_rgba(rgba, out_path)
    return out_path


def render_map_composite(
    scn: Any,
    composite_name: str,
    out_path: Path,
) -> Path:
    """Resample an RGB composite to Pakistan Mercator RGBA PNG."""
    from app.processing.composite_loader import composite_array_from_dataset

    local = _resample_scene_dataset(scn, composite_name)
    try:
        data = composite_array_from_dataset(local)
    except Exception:  # noqa: BLE001
        data = _values(local)
    rgba = _composite_rgb_alpha(data)
    _save_rgba(rgba, out_path)
    return out_path


def ensure_map_overlay_for_product(
    *,
    product_name: str,
    product_kind: str,
    local_image_path: str,
    native_path: Path,
    date: str,
    time: str,
) -> Optional[Path]:
    """
    Ensure `{name}_map.png` exists next to the gallery PNG.
    Generates via satpy resample if missing. Returns path or None on failure.
    """
    from app.processing.reader import load_scene, resolve_dataset_name

    img = Path(local_image_path)
    out = map_path_for_image(img)
    if out.exists() and out.stat().st_size > 0:
        return out

    if not native_path.exists():
        logger.warning("Cannot build map overlay: native missing %s", native_path)
        return None

    with _MAP_OVERLAY_LOCK:
        # Another request may have finished while we waited for the lock.
        if out.exists() and out.stat().st_size > 0:
            return out

        try:
            from app.processing.composite_loader import (
                NORTH_UP_CORNER,
                load_composite_dataset,
            )

            scn = load_scene(native_path, date, time)
            if product_kind == "channel":
                satpy_name = resolve_dataset_name(scn, product_name) or product_name
                scn.load([satpy_name], upper_right_corner=NORTH_UP_CORNER)
                render_map_channel(scn, satpy_name, product_name, out)
            else:
                load_composite_dataset(scn, product_name)
                render_map_composite(scn, product_name, out)
            return out if out.exists() else None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Map overlay failed for %s (%s): %s", product_name, product_kind, exc
            )
            return None
