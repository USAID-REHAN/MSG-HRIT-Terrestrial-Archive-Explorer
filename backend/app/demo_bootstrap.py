"""Install bundled demo data on first run (clone-and-browse without archive access)."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path

from app.config import Settings

logger = logging.getLogger(__name__)

_DEMO_MARK = "demo_bundle_version"
_DEMO_VERSION = "2026-06-22-v1"


def _rewrite_paths_to_absolute(db_path: Path, data_root: Path) -> None:
    """Convert relative demo paths in SQLite to absolute paths for this machine."""
    data_root = data_root.resolve()
    conn = sqlite3.connect(db_path)
    try:
        for table, column in (
            ("timeslots", "local_raw_path"),
            ("products", "local_image_path"),
            ("products", "local_thumbnail_path"),
        ):
            rows = conn.execute(
                f"SELECT rowid, {column} FROM {table} WHERE {column} IS NOT NULL"
            ).fetchall()
            for rowid, value in rows:
                if not value:
                    continue
                p = Path(value)
                if p.is_absolute():
                    abs_path = str(p.resolve())
                else:
                    abs_path = str((data_root / p).resolve())
                conn.execute(
                    f"UPDATE {table} SET {column} = ? WHERE rowid = ?",
                    (abs_path, rowid),
                )
        conn.commit()
    finally:
        conn.close()


def install_demo_bundle_if_needed(settings: Settings) -> bool:
    """
    Copy `data/demo/` into the live data root when no catalog exists yet.
    Returns True when a fresh demo catalog was installed.
    """
    demo_root = settings.data_root / "demo"
    demo_catalog = demo_root / "catalog.sqlite3"
    if settings.db_path.exists() or not demo_catalog.exists():
        return False

    settings.ensure_data_dirs()
    logger.info("Installing bundled demo data from %s", demo_root)

    for sub in ("raw", "processed", "thumbnails"):
        src = demo_root / sub
        if not src.exists():
            continue
        dest = settings.data_root / sub
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest, dirs_exist_ok=True)

    shutil.copy2(demo_catalog, settings.db_path)
    _rewrite_paths_to_absolute(settings.db_path, settings.data_root)

    mark = settings.data_root / _DEMO_MARK
    mark.write_text(_DEMO_VERSION, encoding="utf-8")
    logger.info("Demo bundle installed (%s)", _DEMO_VERSION)
    return True
