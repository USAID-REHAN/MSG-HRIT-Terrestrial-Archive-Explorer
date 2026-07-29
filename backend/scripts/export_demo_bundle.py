#!/usr/bin/env python3
"""
Export a clone-friendly demo bundle for one archive date.

Default: 2026-06-22 with daytime / twilight / nighttime sample timeslots
(09-00, 14-00, 20-00) plus full discovered timeslot metadata for that day.

Output: data/demo/{raw,processed,thumbnails,catalog.sqlite3,README.md}
Paths inside the catalog are stored relative to DATA_ROOT so bootstrap can
rewrite them for any machine.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

# Allow `python backend/scripts/export_demo_bundle.py` from repo root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402

DEFAULT_DATE = "2026-06-22"
DEFAULT_SAMPLE_TIMES = ("09-00", "14-00", "20-00")


def _rel(data_root: Path, path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    try:
        return p.relative_to(data_root).as_posix()
    except ValueError:
        return path.replace("\\", "/")


def export_demo(
    *,
    date: str,
    sample_times: tuple[str, ...],
    dest: Path,
    data_root: Path,
    source_db: Path,
) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    # Copy binary assets for sample timeslots only (msg15.nat — skip duplicate long names).
    for sub in ("raw", "processed", "thumbnails"):
        for t in sample_times:
            src = data_root / sub / "2026" / date / t
            if not src.exists():
                raise FileNotFoundError(f"Missing {src}")
            out = dest / sub / "2026" / date / t
            if sub == "raw":
                out.parent.mkdir(parents=True, exist_ok=True)
                out.mkdir(parents=True, exist_ok=True)
                nat = src / "msg15.nat"
                if not nat.exists():
                    raise FileNotFoundError(f"Missing {nat}")
                shutil.copy2(nat, out / "msg15.nat")
            else:
                shutil.copytree(src, out, dirs_exist_ok=True)

    src = sqlite3.connect(source_db)
    dst = sqlite3.connect(dest / "catalog.sqlite3")
    src.row_factory = sqlite3.Row

    try:
        schema = src.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for row in schema:
            dst.execute(row["sql"])

        # All timeslot rows for the date (browse shows 96/96 discovered).
        timeslots = src.execute(
            "SELECT * FROM timeslots WHERE date = ? ORDER BY time",
            (date,),
        ).fetchall()
        if not timeslots:
            raise RuntimeError(f"No timeslots for {date}")

        sample_ids: list[int] = []
        for ts in timeslots:
            is_sample = ts["time"] in sample_times
            raw_rel = None
            if is_sample:
                raw_rel = f"raw/2026/{date}/{ts['time']}/msg15.nat"
                sample_ids.append(ts["id"])
            dst.execute(
                """
                INSERT INTO timeslots (
                    id, year, date, time, server_relative_path, server_reported_size_bytes,
                    sample_role, download_status, local_raw_path, discovered_at,
                    downloaded_at, last_error
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    ts["id"],
                    ts["year"],
                    ts["date"],
                    ts["time"],
                    ts["server_relative_path"],
                    ts["server_reported_size_bytes"],
                    ts["sample_role"],
                    "downloaded" if is_sample else ts["download_status"],
                    raw_rel,
                    ts["discovered_at"],
                    ts["downloaded_at"] if is_sample else None,
                    None if is_sample else ts["last_error"],
                ),
            )

        placeholders = ",".join("?" * len(sample_ids))
        products = src.execute(
            f"SELECT * FROM products WHERE timeslot_id IN ({placeholders})",
            sample_ids,
        ).fetchall()
        for p in products:
            dst.execute(
                """
                INSERT INTO products (
                    id, timeslot_id, product_name, product_kind, availability_status,
                    local_image_path, local_thumbnail_path, generated_at, error_message
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    p["id"],
                    p["timeslot_id"],
                    p["product_name"],
                    p["product_kind"],
                    p["availability_status"],
                    _rel(data_root, p["local_image_path"]),
                    _rel(data_root, p["local_thumbnail_path"]),
                    p["generated_at"],
                    p["error_message"],
                ),
            )

        # product_reference is re-seeded on startup; jobs omitted (empty dashboard history).
        dst.commit()
    finally:
        src.close()
        dst.close()

    readme = dest / "README.md"
    readme.write_text(
        f"""# Demo data bundle — {date}

Bundled for clone-and-run demos without archive server access.

- **Date:** `{date}`
- **Sample timeslots:** {", ".join(sample_times)} (daytime / twilight / nighttime)
- **Discovered timeslots in catalog:** all slots for this date
- **Products:** full channel + composite set for the three sample timeslots

Installed automatically on first `npm run dev` when `data/catalog.sqlite3` is missing.
""",
        encoding="utf-8",
    )

    total = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    print(f"Demo bundle written to {dest}")
    print(f"  timeslots: {len(timeslots)}")
    print(f"  products: {len(products)}")
    print(f"  total size: {total / (1024**3):.2f} GB")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export demo data bundle for one date")
    parser.add_argument("--date", default=DEFAULT_DATE)
    parser.add_argument(
        "--times",
        nargs="+",
        default=list(DEFAULT_SAMPLE_TIMES),
        help="Sample times (HH-MM) to include raw/processed/thumbnail files for",
    )
    args = parser.parse_args()

    settings = get_settings()
    export_demo(
        date=args.date,
        sample_times=tuple(args.times),
        dest=settings.data_root / "demo",
        data_root=settings.data_root,
        source_db=settings.db_path,
    )


if __name__ == "__main__":
    main()
