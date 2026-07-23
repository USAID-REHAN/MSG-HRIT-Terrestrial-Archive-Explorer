"""Bounded, deduplicated background generation for product globe layers."""

from __future__ import annotations

import json
import logging
import math
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from app.config import Settings
from app.processing.globe_layers import (
    ELIGIBLE_GLOBE_PRODUCTS,
    GLOBE_LAYER_VERSION,
    generate_globe_layer,
    globe_output_paths,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GlobeGenerationRequest:
    product_id: int
    product_name: str
    availability_status: str
    product_error: str | None
    native_path: Path | None
    year: str
    date: str
    time: str


@dataclass(frozen=True)
class GlobeState:
    status: str
    metadata: dict[str, Any] | None = None
    error: str | None = None


def _confined_output_paths(
    settings: Settings, request: GlobeGenerationRequest
) -> tuple[Path, Path]:
    png, sidecar = globe_output_paths(
        settings.processed_dir,
        year=request.year,
        date=request.date,
        time=request.time,
        product=request.product_name,
    )
    root = settings.processed_dir.resolve()
    for path in (png, sidecar):
        try:
            path.resolve().relative_to(root)
        except ValueError as exc:
            raise ValueError("Globe output path escapes the processed directory") from exc
    return png, sidecar


def validate_globe_artifact(
    settings: Settings, request: GlobeGenerationRequest
) -> tuple[Path, dict[str, Any]]:
    """Return a committed globe artifact only when its sidecar and PNG agree."""
    png, sidecar = _confined_output_paths(settings, request)
    if not sidecar.is_file() or not png.is_file():
        raise FileNotFoundError("Globe PNG and sidecar have not been generated")

    try:
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Globe sidecar is unreadable or invalid JSON") from exc
    if not isinstance(metadata, dict):
        raise ValueError("Globe sidecar must contain a JSON object")
    if metadata.get("version") != GLOBE_LAYER_VERSION:
        raise ValueError("Globe sidecar version does not match this backend")
    if metadata.get("product") != request.product_name:
        raise ValueError("Globe sidecar product does not match the requested product")

    bounds = metadata.get("bounds")
    if not isinstance(bounds, dict) or bounds.get("semantics") != "pixel_edges":
        raise ValueError("Globe sidecar bounds are invalid")
    values: dict[str, float] = {}
    for key in ("west", "south", "east", "north"):
        value = bounds.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Globe sidecar bounds are invalid")
        values[key] = float(value)
    if (
        not all(math.isfinite(value) for value in values.values())
        or not -180.0 <= values["west"] < values["east"] <= 180.0
        or not -90.0 <= values["south"] < values["north"] <= 90.0
    ):
        raise ValueError("Globe sidecar bounds are invalid")

    dimensions = metadata.get("dimensions")
    if not isinstance(dimensions, dict):
        raise ValueError("Globe sidecar dimensions are invalid")
    width = dimensions.get("width")
    height = dimensions.get("height")
    if (
        isinstance(width, bool)
        or isinstance(height, bool)
        or not isinstance(width, int)
        or not isinstance(height, int)
        or width < 2
        or height < 2
    ):
        raise ValueError("Globe sidecar dimensions are invalid")
    try:
        with Image.open(png) as image:
            if image.format != "PNG" or image.size != (width, height):
                raise ValueError("Globe PNG does not match its sidecar dimensions")
            image.verify()
    except (OSError, SyntaxError) as exc:
        raise ValueError("Globe PNG is unreadable") from exc
    return png, metadata


class GlobeGenerationManager:
    """Run a small number of expensive Satpy remaps outside request threads."""

    def __init__(self, *, max_workers: int = 2, max_pending: int = 4) -> None:
        if max_workers < 1 or max_pending < max_workers:
            raise ValueError("Invalid globe executor bounds")
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="globe-layer"
        )
        self._capacity = threading.BoundedSemaphore(max_pending)
        self._lock = threading.RLock()
        self._jobs: dict[int, Future[None]] = {}
        self._errors: dict[int, str] = {}

    def status(
        self, request: GlobeGenerationRequest, settings: Settings
    ) -> GlobeState:
        if request.product_name not in ELIGIBLE_GLOBE_PRODUCTS:
            return GlobeState("ineligible", error="Product is not eligible for globe output")
        if request.availability_status == "unavailable_night":
            return GlobeState(
                "unavailable_night",
                error=request.product_error or "Product is unavailable at night",
            )
        if request.availability_status != "generated":
            return GlobeState(
                "error",
                error=request.product_error
                or f"Product is {request.availability_status.replace('_', ' ')}",
            )

        with self._lock:
            future = self._jobs.get(request.product_id)
            saved_error = self._errors.get(request.product_id)
        if future is not None and not future.done():
            return GlobeState("generating")

        try:
            _, metadata = validate_globe_artifact(settings, request)
            return GlobeState("ready", metadata=metadata)
        except FileNotFoundError:
            if saved_error:
                return GlobeState("error", error=saved_error)
            return GlobeState("not_generated")
        except ValueError as exc:
            return GlobeState("error", error=str(exc))

    def start(
        self, request: GlobeGenerationRequest, settings: Settings
    ) -> GlobeState:
        current = self.status(request, settings)
        if current.status not in {"not_generated", "error"}:
            return current
        if request.availability_status != "generated":
            return current
        if request.native_path is None:
            return GlobeState("error", error="Timeslot raw file is not available")
        try:
            _confined_output_paths(settings, request)
        except ValueError as exc:
            return GlobeState("error", error=str(exc))

        with self._lock:
            existing = self._jobs.get(request.product_id)
            if existing is not None and not existing.done():
                return GlobeState("generating")
            if not self._capacity.acquire(blocking=False):
                return GlobeState(
                    "busy", error="Globe generation queue is at capacity; retry shortly"
                )
            self._errors.pop(request.product_id, None)
            try:
                future = self._executor.submit(self._generate, request, settings)
            except Exception:
                self._capacity.release()
                raise
            self._jobs[request.product_id] = future
            future.add_done_callback(
                lambda completed, product_id=request.product_id: self._finished(
                    product_id, completed
                )
            )
        return GlobeState("generating")

    def _generate(
        self, request: GlobeGenerationRequest, settings: Settings
    ) -> None:
        try:
            generate_globe_layer(
                native_path=request.native_path,  # type: ignore[arg-type]
                processed_dir=settings.processed_dir,
                year=request.year,
                date=request.date,
                time=request.time,
                product=request.product_name,
            )
            validate_globe_artifact(settings, request)
        except Exception as exc:
            logger.exception("Globe generation failed for product %s", request.product_id)
            with self._lock:
                self._errors[request.product_id] = str(exc) or type(exc).__name__

    def _finished(self, product_id: int, future: Future[None]) -> None:
        with self._lock:
            if self._jobs.get(product_id) is future:
                self._jobs.pop(product_id, None)
        self._capacity.release()

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)


globe_generation_manager = GlobeGenerationManager()
