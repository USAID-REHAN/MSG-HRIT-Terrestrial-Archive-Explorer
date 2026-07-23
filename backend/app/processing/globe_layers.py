"""Georeferenced, full-visible-disk SEVIRI overlays for 3-D globes.

This module is intentionally independent of the gallery and map-layer paths.
It remaps a loaded SEVIRI dataset to a geographic grid whose bounds are
measured from that dataset's own geostationary ``AreaDefinition``.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from pyresample import create_area_def
from pyresample.geometry import AreaDefinition, StackedAreaDefinition

from app.processing.channels import load_channel_dataset
from app.processing.composite_loader import (
    NORTH_UP_CORNER,
    load_composite_dataset,
)
from app.processing.reader import (
    CHANNEL_NAMES,
    load_scene,
    resolve_dataset_name,
)

GLOBE_LAYER_VERSION = "1.0.0"
GLOBE_RESAMPLER = "bilinear"
# Bilinear's neighbour table scales with target pixels; 2048 px requires
# roughly 1 GiB for a single full-disk layer in the deployed pyresample build.
# 1024 keeps the exact same georeferencing/resampler while remaining bounded.
DEFAULT_GLOBE_WIDTH = 1024
HRV_AGGREGATION_FACTOR = 3
GLOBE_COMPOSITES = frozenset(
    {"natural_color", "airmass", "dust", "ash", "convection"}
)
ELIGIBLE_GLOBE_PRODUCTS = frozenset(CHANNEL_NAMES) | GLOBE_COMPOSITES
# Satpy/pyresample's bilinear LUT builder is not thread-safe. Concurrent
# resamples can expose a partially initialized XArrayBilinearResampler whose
# bilinear_s/bilinear_t arrays are still None.
_BILINEAR_RESAMPLE_LOCK = threading.Lock()


def _computed_array(value: Any) -> np.ndarray:
    if hasattr(value, "compute"):
        value = value.compute()
    return np.asarray(value)


def _json_value(value: Any) -> Any:
    """Convert common NumPy/pyproj metadata values to strict JSON values."""
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, datetime):
        return _utc_iso(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


SourceArea = AreaDefinition | StackedAreaDefinition


def _source_crs_parameters(area: SourceArea) -> dict[str, Any]:
    if isinstance(area, StackedAreaDefinition):
        definitions = list(area.defs)
        if not definitions:
            raise ValueError("Source StackedAreaDefinition has no component areas")
        crs = definitions[0].crs
        if any(definition.crs != crs for definition in definitions[1:]):
            raise ValueError("Source stacked areas do not share one CRS")
    else:
        crs = area.crs
    params = _json_value(crs.to_dict())
    if not isinstance(params, dict):
        raise ValueError("Source AreaDefinition CRS parameters are invalid")
    return params


def _source_longitude(params: dict[str, Any]) -> float:
    value = params.get("lon_0")
    try:
        lon_0 = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Source AreaDefinition CRS has no finite lon_0") from exc
    if not math.isfinite(lon_0) or not -180.0 <= lon_0 <= 180.0:
        raise ValueError("Source AreaDefinition CRS has an invalid lon_0")
    return lon_0


def geographic_bounds_from_area(area: SourceArea) -> dict[str, float]:
    """Measure non-wrapping EPSG:4326 bounds from valid source pixel centres."""
    if not isinstance(area, (AreaDefinition, StackedAreaDefinition)):
        raise TypeError(
            "Globe layers require an AreaDefinition or StackedAreaDefinition"
        )

    crs_params = _source_crs_parameters(area)
    lon_0 = _source_longitude(crs_params)
    lons, lats = area.get_lonlats()
    lon = _computed_array(lons).astype(np.float64, copy=False)
    lat = _computed_array(lats).astype(np.float64, copy=False)
    if lon.shape != lat.shape or lon.ndim != 2:
        raise ValueError("Source longitude/latitude geometry is not a 2-D grid")

    finite = np.isfinite(lon) & np.isfinite(lat)
    if not finite.any():
        raise ValueError("Source AreaDefinition has no finite lon/lat coordinates")
    valid_lon = lon[finite]
    valid_lat = lat[finite]
    if np.any((valid_lat < -90.0) | (valid_lat > 90.0)):
        raise ValueError("Source AreaDefinition contains invalid latitudes")

    # Keep coordinates continuous around the satellite subpoint. A disk that
    # would cross the EPSG:4326 seam is rejected instead of producing a false
    # west/east rectangle.
    relative_lon = ((valid_lon - lon_0 + 180.0) % 360.0) - 180.0
    unwrapped_lon = lon_0 + relative_lon
    west = float(np.min(unwrapped_lon))
    east = float(np.max(unwrapped_lon))
    south = float(np.min(valid_lat))
    north = float(np.max(valid_lat))

    values = (west, south, east, north)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Derived geographic bounds are not finite")
    if west < -180.0 or east > 180.0:
        raise ValueError("Visible disk crosses the EPSG:4326 antimeridian")
    if west >= east or south >= north or east - west >= 180.0:
        raise ValueError("Derived geographic bounds are invalid or wrap longitude")

    return {"west": west, "south": south, "east": east, "north": north}


def geographic_area_for_dataset(
    source_area: SourceArea,
    *,
    width: int = DEFAULT_GLOBE_WIDTH,
) -> tuple[AreaDefinition, dict[str, float]]:
    """Create an EPSG:4326 target with equal angular x/y pixel resolution."""
    if isinstance(width, bool) or not isinstance(width, int) or width < 2:
        raise ValueError("Globe layer width must be an integer of at least 2")
    bounds = geographic_bounds_from_area(source_area)
    lon_span = bounds["east"] - bounds["west"]
    lat_span = bounds["north"] - bounds["south"]
    height = max(2, int(round(width * lat_span / lon_span)))
    target = create_area_def(
        "seviri_full_visible_disk_epsg4326",
        "EPSG:4326",
        width=width,
        height=height,
        area_extent=(
            bounds["west"],
            bounds["south"],
            bounds["east"],
            bounds["north"],
        ),
        units="degrees",
        description="SEVIRI full visible disk measured from source geometry",
    )
    return target, bounds


def _aggregate_hrv_native_grid(dataset: Any) -> Any:
    """Area-average HRV to its native 3 km grid before geographic reprojection.

    IODC HRV is a stacked 1 km scan window. Direct bilinear reprojection makes
    pyresample materialize the full 62-million-pixel geolocation grid. A 3x3
    native-grid mean preserves the source georeferencing and matches SEVIRI's
    standard-channel scale before the one and only CRS-changing resample.
    """
    area = dataset.attrs.get("area")
    if not isinstance(area, StackedAreaDefinition):
        return dataset
    factor = HRV_AGGREGATION_FACTOR
    definitions = list(area.defs)
    if (
        not definitions
        or any(
            definition.width % factor or definition.height % factor
            for definition in definitions
        )
    ):
        raise ValueError("HRV stacked area cannot be aggregated by the declared factor")
    aggregated = dataset.coarsen(
        y=factor, x=factor, boundary="exact"
    ).mean(keep_attrs=True)
    aggregated_defs = [
        AreaDefinition(
            definition.area_id,
            definition.description,
            definition.proj_id,
            definition.crs,
            definition.width // factor,
            definition.height // factor,
            definition.area_extent,
        )
        for definition in definitions
    ]
    aggregated.attrs["area"] = StackedAreaDefinition(*aggregated_defs)
    return aggregated


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _source_timestamp(dataset: Any, date: str, time: str) -> str:
    for key in ("start_time", "nominal_start_time", "end_time"):
        value = dataset.attrs.get(key)
        if isinstance(value, datetime):
            return _utc_iso(value)
    normalized_time = time.replace("-", ":")
    parsed = datetime.fromisoformat(f"{date}T{normalized_time}:00+00:00")
    return _utc_iso(parsed)


def globe_output_paths(
    processed_dir: Path,
    *,
    year: str,
    date: str,
    time: str,
    product: str,
) -> tuple[Path, Path]:
    directory = processed_dir / year / date / time / "globe"
    return directory / f"{product}.png", directory / f"{product}.json"


def _atomic_write_pair(image: Image.Image, metadata: dict[str, Any], png: Path, sidecar: Path) -> None:
    """Publish PNG first and JSON last; the sidecar acts as the commit marker."""
    png.parent.mkdir(parents=True, exist_ok=True)
    png_tmp: Path | None = None
    json_tmp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".png.tmp", dir=png.parent, delete=False
        ) as handle:
            png_tmp = Path(handle.name)
            image.save(handle, format="PNG", optimize=True)
            handle.flush()
            os.fsync(handle.fileno())
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json.tmp",
            dir=sidecar.parent,
            encoding="utf-8",
            newline="\n",
            delete=False,
        ) as handle:
            json_tmp = Path(handle.name)
            json.dump(metadata, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        # A pair cannot be replaced atomically on common filesystems. Remove
        # the old commit marker so an interrupted publish is never mistaken
        # for a complete, internally consistent PNG/JSON pair.
        sidecar.unlink(missing_ok=True)
        os.replace(png_tmp, png)
        png_tmp = None
        os.replace(json_tmp, sidecar)
        json_tmp = None
    finally:
        if png_tmp is not None:
            png_tmp.unlink(missing_ok=True)
        if json_tmp is not None:
            json_tmp.unlink(missing_ok=True)


def generate_globe_layer(
    *,
    native_path: Path,
    processed_dir: Path,
    year: str,
    date: str,
    time: str,
    product: str,
    width: int = DEFAULT_GLOBE_WIDTH,
) -> tuple[Path, Path]:
    """Generate one transparent EPSG:4326 PNG and its georeferencing sidecar."""
    if product not in ELIGIBLE_GLOBE_PRODUCTS:
        raise ValueError(f"Product is not eligible for globe output: {product}")

    scene = load_scene(native_path, date, time)
    if product in CHANNEL_NAMES:
        dataset_name = resolve_dataset_name(scene, product) or product
        dataset = load_channel_dataset(scene, dataset_name)
        product_kind = "channel"
    else:
        dataset_name = product
        dataset = load_composite_dataset(scene, product)
        product_kind = "composite"

    source_area = dataset.attrs.get("area")
    if not isinstance(source_area, (AreaDefinition, StackedAreaDefinition)):
        raise TypeError(
            f"{product} does not have an AreaDefinition or StackedAreaDefinition"
        )
    target_area, bounds = geographic_area_for_dataset(source_area, width=width)

    resample_dataset = dataset
    preprocessing: dict[str, Any] | None = None
    if product == "HRV" and isinstance(source_area, StackedAreaDefinition):
        resample_dataset = _aggregate_hrv_native_grid(dataset)
        scene[dataset_name] = resample_dataset
        preprocessing = {
            "operation": "native_grid_block_mean",
            "factor_y": HRV_AGGREGATION_FACTOR,
            "factor_x": HRV_AGGREGATION_FACTOR,
            "reason": "memory-bounded HRV aggregation before geographic reprojection",
        }

    # Deliberately no exception handler or nearest-neighbour fallback here.
    with _BILINEAR_RESAMPLE_LOCK:
        remapped_scene = scene.resample(
            target_area,
            datasets=[dataset_name],
            resampler=GLOBE_RESAMPLER,
        )
    remapped = remapped_scene[dataset_name]

    # Satpy owns both channel and composite enhancement. fill_value=None in
    # pil_image creates alpha=0 for invalid/outside-disk pixels.
    from satpy.enhancements.enhancer import get_enhanced_image

    enhanced = get_enhanced_image(remapped)
    image = enhanced.pil_image(fill_value=None).convert("RGBA")
    if image.size != (target_area.width, target_area.height):
        raise RuntimeError("Enhanced image dimensions do not match target area")

    source_crs = _source_crs_parameters(source_area)
    enhancement_history = enhanced.data.attrs.get("enhancement_history", [])
    metadata = {
        "version": GLOBE_LAYER_VERSION,
        "product": product,
        "product_kind": product_kind,
        "source_timestamp": _source_timestamp(dataset, date, time),
        "bounds": {
            **bounds,
            "semantics": "pixel_edges",
        },
        "dimensions": {
            "width": target_area.width,
            "height": target_area.height,
        },
        "target_crs": "EPSG:4326",
        "source_crs_parameters": source_crs,
        "source_longitude_of_projection_origin": _source_longitude(source_crs),
        "resampler": GLOBE_RESAMPLER,
        "preprocessing": preprocessing,
        "enhancement": {
            "identity": "satpy.enhancements.enhancer.get_enhanced_image",
            "mode": "default",
            "dataset": dataset_name,
            "history": _json_value(enhancement_history),
        },
        "orientation": {
            "upper_right_corner": NORTH_UP_CORNER,
            "north_up": True,
            "east_right": True,
        },
    }
    png, sidecar = globe_output_paths(
        processed_dir,
        year=year,
        date=date,
        time=time,
        product=product,
    )
    _atomic_write_pair(image, metadata, png, sidecar)
    return png, sidecar
