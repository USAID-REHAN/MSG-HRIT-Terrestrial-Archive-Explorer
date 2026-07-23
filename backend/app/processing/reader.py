"""satpy native-format Scene loading for msg15.nat (BUILDPLAN §10 Step 4)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from app.processing.composite_catalog import COMPOSITE_NAMES
from app.processing.composite_loader import NORTH_UP_CORNER, ensure_satpy_config_path

logger = logging.getLogger(__name__)

CHANNEL_NAMES = [
    "HRV",
    "VIS006",
    "VIS008",
    "IR_016",
    "IR_039",
    "WV_062",
    "WV_073",
    "IR_087",
    "IR_097",
    "IR_108",
    "IR_120",
    "IR_134",
]

# Mapping our names → common satpy SEVIRI native names
SATPY_CHANNEL_ALIASES: dict[str, list[str]] = {
    "HRV": ["HRV"],
    "VIS006": ["VIS006", "VIS6"],
    "VIS008": ["VIS008", "VIS8"],
    "IR_016": ["IR_016", "IR1.6", "IR016"],
    "IR_039": ["IR_039", "IR3.9", "IR039"],
    "WV_062": ["WV_062", "WV_62", "WV6.2"],
    "WV_073": ["WV_073", "WV_73", "WV7.3"],
    "IR_087": ["IR_087", "IR8.7", "IR087"],
    "IR_097": ["IR_097", "IR9.7", "IR097"],
    "IR_108": ["IR_108", "IR10.8", "IR108"],
    "IR_120": ["IR_120", "IR12.0", "IR120"],
    "IR_134": ["IR_134", "IR13.4", "IR134"],
}


def satpy_alias_path(nat_path: Path, date: str, time: str) -> Path:
    """
    satpy's seviri_l1b_native reader only accepts EUMETSAT-style filenames,
    not the archive's literal `msg15.nat`. Create a same-directory hardlink
    (or copy fallback) with a pattern-matching name derived from the timeslot.
    Keeps the original msg15.nat on disk per BUILDPLAN layout.
    """
    y, m, d = date.split("-")
    hh, mm = time.replace(":", "-").split("-")
    stamp = f"{y}{m}{d}{hh}{mm}00"
    alias_name = f"MSG3-SEVI-MSG15-0100-NA-{stamp}.000000000Z-NA.nat"
    alias = nat_path.parent / alias_name
    src_size = nat_path.stat().st_size

    if alias.exists():
        try:
            if alias.stat().st_size == src_size:
                return alias
            alias.unlink(missing_ok=True)
        except OSError:
            pass

    try:
        os.link(nat_path, alias)
    except OSError:
        import shutil

        shutil.copy2(nat_path, alias)
    return alias


def load_scene(nat_path: Path, date: str, time: str):
    """Load a single .nat file with satpy's native reader (north-up ready)."""
    ensure_satpy_config_path()
    from satpy import Scene

    alias = satpy_alias_path(nat_path, date, time)
    scn = Scene(filenames=[str(alias)], reader="seviri_l1b_native")
    return scn


def available_datasets(scn) -> set[str]:
    """Return normalized product names available (or loadable) in the Scene."""
    names: set[str] = set()
    try:
        available = scn.available_dataset_names()
    except Exception:  # noqa: BLE001
        available = []
    avail_set = set(available)

    for our_name, aliases in SATPY_CHANNEL_ALIASES.items():
        if any(a in avail_set for a in aliases):
            names.add(our_name)

    try:
        composites = set(scn.available_composite_names())
    except Exception:  # noqa: BLE001
        composites = set()
    for c in COMPOSITE_NAMES:
        if c in composites:
            names.add(c)

    return names


def resolve_dataset_name(scn, our_name: str) -> Optional[str]:
    aliases = SATPY_CHANNEL_ALIASES.get(our_name, [our_name])
    try:
        available = set(scn.available_dataset_names())
    except Exception:  # noqa: BLE001
        available = set()
    for a in aliases:
        if a in available:
            return a
    if our_name in available:
        return our_name
    return None


def try_load(scn, names: list[str]) -> Any:
    scn.load(names, upper_right_corner=NORTH_UP_CORNER)
    return scn
