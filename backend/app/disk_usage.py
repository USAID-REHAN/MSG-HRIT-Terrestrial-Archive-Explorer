"""Cached local disk usage — never blocks the dashboard request path.

Heavy directory walks run only when explicitly requested (GET /api/disk-usage)
or after download/processing invalidates the cache and a refresh is asked for.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.config import Settings, get_settings
from app.downloader.worker import free_disk_gb

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 120.0


@dataclass(frozen=True)
class DiskUsageSnapshot:
    raw_bytes: int
    processed_bytes: int
    thumbnails_bytes: int
    catalog_bytes: int
    total_bytes: int
    free_gb: float
    computed_at: float
    stale: bool = False


_lock = threading.Lock()
_cache: Optional[DiskUsageSnapshot] = None
_refreshing = False


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    except OSError as exc:
        logger.warning("disk walk failed for %s: %s", path, exc)
    return total


def _compute(settings: Settings) -> DiskUsageSnapshot:
    raw_bytes = _dir_size(settings.raw_dir)
    processed_bytes = _dir_size(settings.processed_dir)
    thumbnails_bytes = _dir_size(settings.thumbnails_dir)
    catalog_bytes = 0
    if settings.db_path.exists():
        try:
            catalog_bytes = settings.db_path.stat().st_size
        except OSError:
            catalog_bytes = 0
    total = raw_bytes + processed_bytes + thumbnails_bytes + catalog_bytes
    return DiskUsageSnapshot(
        raw_bytes=raw_bytes,
        processed_bytes=processed_bytes,
        thumbnails_bytes=thumbnails_bytes,
        catalog_bytes=catalog_bytes,
        total_bytes=total,
        free_gb=round(free_disk_gb(settings.data_root), 2),
        computed_at=time.time(),
        stale=False,
    )


def _store(snapshot: DiskUsageSnapshot) -> None:
    global _cache, _refreshing
    with _lock:
        _cache = snapshot
        _refreshing = False


def _bg_refresh(settings: Settings) -> None:
    try:
        snap = _compute(settings)
        _store(snap)
        logger.info(
            "Disk usage cache refreshed: total=%.2f GB",
            snap.total_bytes / (1024**3),
        )
    except Exception:  # noqa: BLE001
        logger.exception("Background disk usage refresh failed")
        with _lock:
            global _refreshing
            _refreshing = False


def invalidate_disk_usage_cache() -> None:
    """Mark cache stale after downloads/processing (does not start a walk)."""
    global _cache
    with _lock:
        if _cache is not None:
            _cache = DiskUsageSnapshot(
                raw_bytes=_cache.raw_bytes,
                processed_bytes=_cache.processed_bytes,
                thumbnails_bytes=_cache.thumbnails_bytes,
                catalog_bytes=_cache.catalog_bytes,
                total_bytes=_cache.total_bytes,
                free_gb=_cache.free_gb,
                computed_at=0.0,
                stale=True,
            )


def peek_disk_usage() -> Optional[DiskUsageSnapshot]:
    """Return cache if present — never starts a directory walk."""
    with _lock:
        return _cache


def request_disk_usage_refresh(settings: Settings | None = None) -> Optional[DiskUsageSnapshot]:
    """
    Return cache immediately. If missing/stale, kick a background walk once
    and return whatever we have (possibly None / stale).
    """
    global _refreshing
    settings = settings or get_settings()
    now = time.time()

    with _lock:
        cached = _cache
        refreshing = _refreshing

    need_refresh = cached is None or cached.stale or (
        now - cached.computed_at > _CACHE_TTL_SECONDS
    )
    if need_refresh and not refreshing:
        with _lock:
            if not _refreshing:
                _refreshing = True
                threading.Thread(
                    target=_bg_refresh,
                    args=(settings,),
                    name="disk-usage-refresh",
                    daemon=True,
                ).start()

    return cached


def get_disk_usage_blocking(settings: Settings | None = None) -> DiskUsageSnapshot:
    """Synchronous compute — only for explicit /api/disk-usage?wait=1."""
    settings = settings or get_settings()
    snap = _compute(settings)
    _store(snap)
    return snap
