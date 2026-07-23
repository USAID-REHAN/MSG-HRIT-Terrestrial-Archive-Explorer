"""Load SEVIRI composites with north-up orientation and IR-grid resampling."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# North-up + east-right (Russia / Europe at top, Antarctica toward bottom).
NORTH_UP_CORNER = "NE"

_CONFIG_DIR = Path(__file__).resolve().parent / "satpy_config"


class CompositeLoadContext:
    """Per-timeslot cache for the expensive IR-grid resampled Scene."""

    def __init__(self, scene: Any) -> None:
        self.scene = scene
        self.resampled_scene: Any | None = None

    def prepare(self, names: list[str]) -> None:
        """Load all lazy prerequisites before building the shared resampled Scene."""
        for name in names:
            try:
                self.scene.load([name], upper_right_corner=NORTH_UP_CORNER)
            except Exception:  # noqa: BLE001
                logger.debug("Composite %s needs fallback or is unavailable", name)

    def load(self, name: str) -> Any:
        ensure_satpy_config_path()
        self.scene.load([name], upper_right_corner=NORTH_UP_CORNER)
        if name in self.scene:
            return self.scene[name]

        if self.resampled_scene is None:
            self.resampled_scene = self.scene.resample(_ensure_ir_area(self.scene))
        self.resampled_scene.load([name])
        if name not in self.resampled_scene:
            raise RuntimeError(f"Composite {name} missing after resample to IR grid")
        self.scene[name] = self.resampled_scene[name]
        return self.resampled_scene[name]


def ensure_satpy_config_path() -> None:
    """Prepend our local satpy extras so custom composites are discoverable."""
    root = str(_CONFIG_DIR)
    existing = os.environ.get("SATPY_CONFIG_PATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    if root not in parts:
        os.environ["SATPY_CONFIG_PATH"] = (
            root if not parts else root + os.pathsep + existing
        )


def _ensure_ir_area(scn: Any):
    """Return the ~3 km IR AreaDefinition, loading IR_108 if needed."""
    from pyresample.geometry import AreaDefinition, StackedAreaDefinition

    for key in list(scn.keys()):
        area = scn[key].attrs.get("area")
        if isinstance(area, AreaDefinition) and not isinstance(area, StackedAreaDefinition):
            shape = getattr(area, "shape", None)
            if shape and max(shape) <= 5000:
                return area
    scn.load(["IR_108"], upper_right_corner=NORTH_UP_CORNER)
    return scn["IR_108"].attrs["area"]


def load_composite_dataset(
    scn: Any, name: str, context: CompositeLoadContext | None = None
) -> Any:
    """
    Load one composite from an already-opened Scene.

    Forces north-up orientation. Mixed-resolution recipes (HRV + IR) are
    resampled onto the IR full-disk grid, then regenerated so band shapes align.
    """
    return (context or CompositeLoadContext(scn)).load(name)


def composite_array_from_dataset(dataset) -> np.ndarray:
    """Return (y, x, 3) float array in roughly 0–1; enhance for colour.

    Full-disk SEVIRI RGBs look correct after satpy enhancement; raw channel
    combos can exceed 1.0 and render as washed or black cyan blobs.
    """

    def _to_yx3(arr: np.ndarray) -> np.ndarray:
        arr = np.asarray(arr, dtype=np.float64)
        if arr.ndim == 3 and arr.shape[0] in (1, 2, 3, 4) and arr.shape[0] < min(arr.shape[1:]):
            arr = np.moveaxis(arr, 0, -1)
        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr], axis=-1)
        if arr.ndim == 3 and arr.shape[-1] == 1:
            g = arr[..., 0]
            arr = np.stack([g, g, g], axis=-1)
        if arr.ndim == 3 and arr.shape[-1] == 2:
            arr = np.concatenate([arr, arr[..., 1:2]], axis=-1)
        if arr.ndim == 3 and arr.shape[-1] == 4:
            arr = arr[..., :3]
        return arr

    try:
        from satpy.enhancements.enhancer import get_enhanced_image

        img = get_enhanced_image(dataset)
        data = img.data
        if hasattr(data, "compute"):
            data = data.compute()
        enhanced = _to_yx3(np.asarray(data, dtype=np.float32))
        if enhanced.ndim == 3 and enhanced.shape[-1] == 3:
            return enhanced
    except Exception:  # noqa: BLE001
        logger.debug(
            "Enhancement failed for %s; using raw values",
            getattr(dataset, "attrs", {}),
        )

    vals = dataset.values
    if hasattr(vals, "compute"):
        vals = vals.compute()
    return _to_yx3(np.asarray(vals, dtype=np.float32))


def composite_arrays_from_datasets(datasets: list[Any]) -> list[np.ndarray]:
    """Enhance and compute a small batch in one Dask graph execution."""
    from satpy.enhancements.enhancer import get_enhanced_image

    lazy = [get_enhanced_image(dataset).data for dataset in datasets]
    try:
        import dask

        computed = dask.compute(*lazy)
    except ImportError:
        computed = tuple(x.compute() if hasattr(x, "compute") else x for x in lazy)

    arrays: list[np.ndarray] = []
    for value in computed:
        arr = np.asarray(value, dtype=np.float32)
        if arr.ndim == 3 and arr.shape[0] in (1, 2, 3, 4) and arr.shape[0] < min(arr.shape[1:]):
            arr = np.moveaxis(arr, 0, -1)
        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr], axis=-1)
        if arr.ndim == 3 and arr.shape[-1] == 1:
            arr = np.repeat(arr, 3, axis=-1)
        if arr.ndim == 3 and arr.shape[-1] == 2:
            arr = np.concatenate([arr, arr[..., 1:2]], axis=-1)
        if arr.ndim == 3 and arr.shape[-1] == 4:
            arr = arr[..., :3]
        arrays.append(arr)
    return arrays


def is_nightish_composite_error(name: str, exc: BaseException, solar_set: frozenset) -> bool:
    msg = str(exc).lower()
    if name in solar_set:
        return any(
            k in msg
            for k in (
                "missing",
                "solar",
                "vis",
                "day",
                "night",
                "not available",
                "unknown datasets",
                "require resampling",
                "shapes do not align",
            )
        )
    return False
