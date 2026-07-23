"""Lightweight archive-server reachability check (does not download .nat files)."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.api.schemas import ConnectivityStatus
from app.config import Settings, get_settings

_CACHE_TTL_SECONDS = 20.0
_lock = threading.Lock()
_cache: Optional[ConnectivityStatus] = None
_cache_at = 0.0


def check_archive_connectivity(
    settings: Settings | None = None,
    *,
    timeout_seconds: float = 1.2,
    use_cache: bool = True,
) -> ConnectivityStatus:
    global _cache, _cache_at
    settings = settings or get_settings()
    now = time.time()

    if use_cache:
        with _lock:
            if _cache is not None and (now - _cache_at) < _CACHE_TTL_SECONDS:
                return _cache

    url = settings.archive_url
    checked_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            resp = client.head(url)
            # Some directory servers reject HEAD — fall back to a tiny GET
            if resp.status_code in (405, 501):
                resp = client.get(url)
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            # 2xx/3xx = reachable; 4xx/5xx still means the host answered
            reachable = resp.status_code < 500
            result = ConnectivityStatus(
                reachable=reachable,
                archive_url=url,
                latency_ms=latency_ms,
                checked_at=checked_at,
                error=None if reachable else f"HTTP {resp.status_code}",
                http_status=resp.status_code,
            )
    except Exception as exc:  # noqa: BLE001
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        result = ConnectivityStatus(
            reachable=False,
            archive_url=url,
            latency_ms=latency_ms,
            checked_at=checked_at,
            error=str(exc),
            http_status=None,
        )

    with _lock:
        _cache = result
        _cache_at = time.time()
    return result
