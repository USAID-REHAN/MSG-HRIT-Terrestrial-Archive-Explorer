"""Catalog integrity checks that do not render or process satellite data."""

from __future__ import annotations

from pathlib import Path

from app.processing.composite_catalog import (
    COMPOSITE_LABELS,
    COMPOSITE_NAMES,
    SOLAR_DEPENDENT_COMPOSITES,
)


CONFIG = (
    Path(__file__).parents[1]
    / "app"
    / "processing"
    / "satpy_config"
    / "composites"
    / "seviri.yaml"
)


def _inline_recipe_signature(text: str, name: str) -> tuple[str, ...]:
    lines = text.splitlines()
    start = lines.index(f"  {name}:")
    for line in lines[start + 1 :]:
        if line.startswith("  ") and not line.startswith("    "):
            break
        prefix = "    prerequisites: ["
        if line.startswith(prefix) and line.endswith("]"):
            return tuple(item.strip() for item in line[len(prefix) : -1].split(","))
    raise AssertionError(f"{name} has no inline prerequisite recipe")


def test_catalog_contains_100_unique_named_composites():
    assert len(COMPOSITE_NAMES) == 100
    assert len(set(COMPOSITE_NAMES)) == 100
    assert set(COMPOSITE_NAMES) == set(COMPOSITE_LABELS)


def test_added_composites_have_unique_local_recipes():
    text = CONFIG.read_text(encoding="utf-8")
    added = COMPOSITE_NAMES[50:]
    signatures = [_inline_recipe_signature(text, name) for name in added]
    native_channels = {
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
    }

    assert len(added) == 50
    assert len(set(signatures)) == 50
    assert all(len(signature) == 3 for signature in signatures)
    assert all(set(signature).issubset(native_channels) for signature in signatures)


def test_added_daylight_recipes_are_classified_as_solar_dependent():
    assert set(COMPOSITE_NAMES[91:]).issubset(SOLAR_DEPENDENT_COMPOSITES)
