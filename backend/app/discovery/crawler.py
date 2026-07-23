"""
Crawl HRIT_Native/<year>/<date>/<time>/ for msg15.nat listings (BUILDPLAN §10 Step 1).

Reads only HTML directory listings — never downloads .nat files.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Timeslot

logger = logging.getLogger(__name__)

# Match hrefs like "2026/" or "2026-06-22/" or "09-00/"
_DIR_HREF = re.compile(r"^([^?/]+)/$")
_SIZE_RE = re.compile(r"([\d.]+)\s*([KMGT]?B)", re.I)

ProgressCallback = Callable[[int, int, str], None]


def _parse_size_from_listing_row(text: str) -> Optional[int]:
    """Best-effort parse of Apache/nginx-style directory listing size."""
    # Common patterns: "271M", "271 MB", "284164096"
    m = re.search(r"\b(\d{6,})\b", text.replace(",", ""))
    if m:
        return int(m.group(1))

    m = _SIZE_RE.search(text.replace(",", ""))
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2).upper()
    mult = {
        "B": 1,
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
    }.get(unit, 1)
    return int(value * mult)


def list_directory(client: httpx.Client, url: str) -> list[tuple[str, Optional[int]]]:
    """
    Return list of (name, size_bytes_or_None) for entries in an HTML listing.
    Directories keep a trailing slash in the name.
    """
    resp = client.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    results: list[tuple[str, Optional[int]]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href in ("../", "./", "/") or href.startswith("?"):
            continue
        # Skip parent links
        name = href.split("?")[0]
        if name in ("../", "./"):
            continue

        # Try to get size from the parent row text
        size: Optional[int] = None
        parent = a.parent
        row_text = ""
        if parent is not None:
            row_text = parent.get_text(" ", strip=True)
            # Prefer <tr> if available
            tr = a.find_parent("tr")
            if tr is not None:
                row_text = tr.get_text(" ", strip=True)
            size = _parse_size_from_listing_row(row_text)

        results.append((name, size))
    return results


def _is_year(name: str) -> bool:
    return bool(re.fullmatch(r"\d{4}/?", name.rstrip("/")))


def _is_date(name: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}/?", name.rstrip("/")))


def _is_time(name: str) -> bool:
    return bool(re.fullmatch(r"\d{2}-\d{2}/?", name.rstrip("/")))


def _scan_date(
    client: httpx.Client, year: str, date: str, date_url: str
) -> tuple[str, str, list[tuple[str, str, Optional[int]]]]:
    found: list[tuple[str, str, Optional[int]]] = []
    for name, _ in list_directory(client, date_url):
        if not _is_time(name):
            continue
        time_str = name.rstrip("/")
        time_url = urljoin(date_url, name if name.endswith("/") else name + "/")
        for fname, file_size in list_directory(client, time_url):
            if fname.rstrip("/").lower() == "msg15.nat":
                found.append(
                    (time_str, f"{year}/{date}/{time_str}/msg15.nat", file_size)
                )
                break
    return year, date, found


def discover_archive(
    db: Session,
    settings: Optional[Settings] = None,
    progress: Optional[ProgressCallback] = None,
    client: Optional[httpx.Client] = None,
) -> dict:
    """
    Walk the entire HRIT_Native tree and upsert timeslots as 'discovered'.

    Safe to re-run: existing rows are updated (size path) but not duplicated;
    sample_role / download_status of already-progressed rows are left alone
    except we refresh server_reported_size_bytes when present.
    """
    settings = settings or get_settings()
    own_client = client is None
    client = client or httpx.Client(timeout=60.0, follow_redirects=True)

    root = settings.archive_url
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    new_count = 0
    updated_count = 0
    scanned_dates = 0

    try:
        if progress:
            progress(0, 0, f"Listing years at {root}")

        years = [
            (n.rstrip("/"), n)
            for n, _ in list_directory(client, root)
            if _is_year(n)
        ]
        years.sort()

        # Pre-count dates for progress (best effort)
        date_entries: list[tuple[str, str, str]] = []  # year, date, date_url
        for year, year_slash in years:
            year_url = urljoin(root, year_slash if year_slash.endswith("/") else year + "/")
            for name, _ in list_directory(client, year_url):
                if _is_date(name):
                    date = name.rstrip("/")
                    date_url = urljoin(year_url, name if name.endswith("/") else name + "/")
                    date_entries.append((year, date, date_url))

        total_dates = len(date_entries)
        if progress:
            progress(0, total_dates, f"Found {len(years)} year(s), {total_dates} date folder(s)")

        existing_by_key = {
            (row.year, row.date, row.time): row
            for row in db.execute(select(Timeslot)).scalars().all()
        }
        with ThreadPoolExecutor(max_workers=settings.discovery_workers) as pool:
            futures = {
                pool.submit(_scan_date, client, year, date, date_url): date
                for year, date, date_url in date_entries
            }
            for future in as_completed(futures):
                year, date, discovered = future.result()
                scanned_dates += 1
                for time_str, rel_path, file_size in discovered:
                    key = (year, date, time_str)
                    existing = existing_by_key.get(key)
                    if existing is None:
                        existing = Timeslot(
                            year=year,
                            date=date,
                            time=time_str,
                            server_relative_path=rel_path,
                            server_reported_size_bytes=file_size,
                            sample_role=None,
                            download_status="discovered",
                            local_raw_path=None,
                            discovered_at=now,
                            downloaded_at=None,
                            last_error=None,
                        )
                        db.add(existing)
                        existing_by_key[key] = existing
                        new_count += 1
                    else:
                        if file_size is not None:
                            existing.server_reported_size_bytes = file_size
                        existing.server_relative_path = rel_path
                        updated_count += 1
                db.commit()
                if progress:
                    progress(scanned_dates, total_dates, f"Scanned {date}")

        if progress:
            progress(total_dates, total_dates, f"Discovery done: +{new_count} new, {updated_count} refreshed")

        return {
            "years_scanned": len(years),
            "dates_scanned": scanned_dates,
            "new_timeslots": new_count,
            "updated_timeslots": updated_count,
        }
    finally:
        if own_client:
            client.close()
