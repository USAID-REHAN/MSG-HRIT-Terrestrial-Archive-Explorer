"""Bounded, deduplicated background generation for Mercator map overlays.

Long synchronous POST /ensure calls previously held Next.js proxy sockets open
for minutes and crashed under concurrent satpy loads (ECONNRESET / 500s).
Generation now runs in a single worker; HTTP endpoints only enqueue / poll.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from app.processing.map_layers import ensure_map_overlay_for_product, map_path_for_image

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MapOverlayRequest:
    product_id: int
    product_name: str
    product_kind: str
    local_image_path: str
    native_path: Path
    date: str
    time: str


@dataclass(frozen=True)
class MapOverlayState:
    status: str  # ready | generating | error | busy | unavailable
    map_image_url: str | None = None
    error: str | None = None


class MapOverlayManager:
    """Run at most one satpy Mercator resample at a time."""

    def __init__(self, *, max_workers: int = 1, max_pending: int = 128) -> None:
        if max_workers < 1 or max_pending < max_workers:
            raise ValueError("Invalid map overlay executor bounds")
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="map-overlay"
        )
        self._capacity = threading.BoundedSemaphore(max_pending)
        self._lock = threading.RLock()
        self._jobs: dict[int, Future[None]] = {}
        self._errors: dict[int, str] = {}

    def status(self, request: MapOverlayRequest) -> MapOverlayState:
        out = map_path_for_image(request.local_image_path)
        if out.exists() and out.stat().st_size > 0:
            return MapOverlayState(
                "ready",
                map_image_url=f"/api/map-images/{request.product_id}",
            )

        with self._lock:
            future = self._jobs.get(request.product_id)
            saved_error = self._errors.get(request.product_id)

        if future is not None and not future.done():
            return MapOverlayState("generating")

        if saved_error:
            return MapOverlayState("error", error=saved_error)

        if not request.native_path.exists():
            return MapOverlayState(
                "unavailable", error="Timeslot raw file not available"
            )

        return MapOverlayState("unavailable", error="Map overlay not generated yet")

    def start(self, request: MapOverlayRequest) -> MapOverlayState:
        current = self.status(request)
        if current.status == "ready":
            return current
        if current.status == "generating":
            return current
        if not request.native_path.exists():
            return MapOverlayState(
                "unavailable", error="Timeslot raw file not available"
            )

        with self._lock:
            existing = self._jobs.get(request.product_id)
            if existing is not None and not existing.done():
                return MapOverlayState("generating")
            if not self._capacity.acquire(blocking=False):
                return MapOverlayState(
                    "busy",
                    error="Map overlay queue is at capacity; retry shortly",
                )
            self._errors.pop(request.product_id, None)
            try:
                future = self._executor.submit(self._generate, request)
            except Exception:
                self._capacity.release()
                raise
            self._jobs[request.product_id] = future
            future.add_done_callback(
                lambda completed, product_id=request.product_id: self._finished(
                    product_id, completed
                )
            )
        return MapOverlayState("generating")

    def _generate(self, request: MapOverlayRequest) -> None:
        path = ensure_map_overlay_for_product(
            product_name=request.product_name,
            product_kind=request.product_kind,
            local_image_path=request.local_image_path,
            native_path=request.native_path,
            date=request.date,
            time=request.time,
        )
        if path is None or not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError(
                f"Failed to resample {request.product_name} to Mercator map overlay"
            )

    def _finished(self, product_id: int, future: Future[None]) -> None:
        try:
            exc = future.exception()
            with self._lock:
                if exc is not None:
                    self._errors[product_id] = str(exc)
                    logger.warning(
                        "Map overlay generation failed for product %s: %s",
                        product_id,
                        exc,
                    )
                else:
                    self._errors.pop(product_id, None)
                self._jobs.pop(product_id, None)
        finally:
            self._capacity.release()


map_overlay_manager = MapOverlayManager()
