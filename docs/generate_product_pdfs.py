#!/usr/bin/env python3
"""
Generate deliverable PDFs for MSG HRIT Terrestrial Archive Explorer:

1) Interpretation & Applications Report (one section per product)
2) Product User Guide (exactly two pages per product)

Outputs land in this docs/ folder. Run from repo root or docs/:

  backend\\.venv\\Scripts\\python docs\\generate_product_pdfs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# --- paths ---
DOCS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DOCS_DIR.parent
BACKEND = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.processing.composite_catalog import COMPOSITE_LABELS, COMPOSITE_NAMES  # noqa: E402
from app.processing.reader import CHANNEL_NAMES  # noqa: E402
from app.reference.product_reference import (  # noqa: E402
    PRODUCT_REFERENCE_SEED,
    SOLAR_DEPENDENT_CHANNELS,
    _auto_composite_seeds,
)

PROCESSED = PROJECT_ROOT / "data" / "processed"
# Prefer a full daytime slot; night as fallback for night-only recipes
PRIMARY_SLOT = PROCESSED / "2026" / "2026-06-22" / "09-00"
FALLBACK_SLOT = PROCESSED / "2026" / "2026-06-22" / "20-00"

OUT_REPORT = DOCS_DIR / "MSG_HRIT_Product_Interpretation_Applications_Report.pdf"
OUT_GUIDE = DOCS_DIR / "MSG_HRIT_Product_User_Guide_Two_Pager.pdf"

# --- palette (matches app liquid-glass: slate + teal, not purple) ---
NAVY = colors.Color(0.07, 0.12, 0.18)
SLATE = colors.Color(0.15, 0.22, 0.30)
TEAL = colors.Color(0.10, 0.55, 0.58)
TEAL_LIGHT = colors.Color(0.85, 0.94, 0.94)
AMBER = colors.Color(0.72, 0.45, 0.12)
WHITE = colors.white
LIGHT_BG = colors.Color(0.96, 0.97, 0.98)
MUTED = colors.Color(0.35, 0.40, 0.45)
RULE = colors.Color(0.75, 0.80, 0.82)

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm


def all_products() -> list[dict]:
    by_name = {r["product_name"]: r for r in PRODUCT_REFERENCE_SEED}
    for r in _auto_composite_seeds():
        by_name.setdefault(r["product_name"], r)
    ordered: list[dict] = []
    for name in CHANNEL_NAMES:
        if name in by_name:
            ordered.append(by_name[name])
    for name in COMPOSITE_NAMES:
        if name in by_name:
            ordered.append(by_name[name])
    return ordered


def product_label(name: str) -> str:
    if name in COMPOSITE_LABELS:
        return COMPOSITE_LABELS[name]
    return name.replace("_", " ")


def find_product_image(name: str) -> Path | None:
    for slot in (PRIMARY_SLOT, FALLBACK_SLOT):
        p = slot / f"{name}.png"
        if p.is_file():
            return p
    # last resort: any processed copy
    matches = list(PROCESSED.rglob(f"{name}.png"))
    # skip map overlays
    matches = [m for m in matches if not m.name.endswith("_map.png")]
    return matches[0] if matches else None


def prepare_image(src: Path, max_w_px: int = 1200, max_h_px: int = 900) -> Path:
    """Downscale large PNGs into docs/_cache for faster PDF embedding."""
    cache = DOCS_DIR / "_image_cache"
    cache.mkdir(exist_ok=True)
    out = cache / f"{src.stem}_{max_w_px}.jpg"
    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        return out
    with PILImage.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((max_w_px, max_h_px), PILImage.Resampling.LANCZOS)
        im.save(out, "JPEG", quality=82, optimize=True)
    return out


def make_styles():
    base = getSampleStyleSheet()
    styles = {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=28,
            textColor=WHITE,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            textColor=TEAL_LIGHT,
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=NAVY,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=TEAL,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12.5,
            textColor=SLATE,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=MUTED,
            spaceAfter=3,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=SLATE,
            spaceAfter=2,
        ),
        "caption": ParagraphStyle(
            "caption",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceBefore=2,
            spaceAfter=6,
        ),
        "sector_title": ParagraphStyle(
            "sector_title",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=NAVY,
            spaceAfter=2,
        ),
        "sector_body": ParagraphStyle(
            "sector_body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10.5,
            textColor=SLATE,
            alignment=TA_JUSTIFY,
        ),
        "toc": ParagraphStyle(
            "toc",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=SLATE,
        ),
        "badge": ParagraphStyle(
            "badge",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=TEAL,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "guide_title": ParagraphStyle(
            "guide_title",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=NAVY,
            spaceAfter=4,
        ),
        "guide_kicker": ParagraphStyle(
            "guide_kicker",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=TEAL,
            spaceAfter=2,
        ),
    }
    return styles


SECTORS = [
    ("Agriculture", "agriculture_application"),
    ("Aviation", "aviation_application"),
    ("Natural Resource Monitoring", "natural_resource_application"),
    ("Natural Disaster Monitoring", "disaster_response_application"),
]


def header_footer_factory(doc_title: str):
    def _draw(canvas, doc):
        canvas.saveState()
        # top rule
        canvas.setStrokeColor(TEAL)
        canvas.setLineWidth(1.6)
        canvas.line(MARGIN, PAGE_H - 12 * mm, PAGE_W - MARGIN, PAGE_H - 12 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, PAGE_H - 10 * mm, "MSG HRIT Terrestrial Archive Explorer")
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 10 * mm, doc_title)
        # bottom
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN, 12 * mm, PAGE_W - MARGIN, 12 * mm)
        canvas.drawCentredString(
            PAGE_W / 2, 8 * mm, f"Page {doc.page}  ·  SATMET internship deliverable"
        )
        canvas.restoreState()

    return _draw


def cover_block(styles, title: str, subtitle: str, bullets: list[str]):
    """Full-bleed-looking cover using a colored table banner."""
    banner = Table(
        [[Paragraph(title, styles["cover_title"])],
         [Paragraph(subtitle, styles["cover_sub"])]],
        colWidths=[PAGE_W - 2 * MARGIN],
    )
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("TOPPADDING", (0, 0), (-1, 0), 28),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 22),
                ("LEFTPADDING", (0, 0), (-1, -1), 18),
                ("RIGHTPADDING", (0, 0), (-1, -1), 18),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    accent = Table([[""]], colWidths=[PAGE_W - 2 * MARGIN], rowHeights=[4])
    accent.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEAL)]))

    story = [Spacer(1, 18 * mm), banner, accent, Spacer(1, 10 * mm)]
    story.append(Paragraph("Document contents", styles["h2"]))
    for b in bullets:
        story.append(Paragraph(f"• {b}", styles["body"]))
    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            "Source: in-app <b>product_reference</b> glossary (SEVIRI channels + satpy/EUMETSAT-style "
            "composites) produced by the MSG HRIT Terrestrial Archive Explorer. Sample imagery from "
            "the curated daytime timeslot <b>2026-06-22 09:00</b> (night fallback 20:00 where needed).",
            styles["small"],
        )
    )
    story.append(PageBreak())
    return story


def image_flowable(path: Path | None, max_w, max_h, styles, caption: str):
    if path is None or not path.exists():
        box = Table(
            [[Paragraph("Sample image not available for this product in the local archive.", styles["small"])]],
            colWidths=[max_w],
            rowHeights=[max_h * 0.35],
        )
        box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
                    ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        return [box, Paragraph(caption, styles["caption"])]

    cached = prepare_image(path)
    img = Image(str(cached))
    img.hAlign = "CENTER"
    # fit
    iw, ih = img.imageWidth, img.imageHeight
    scale = min(max_w / iw, max_h / ih)
    img.drawWidth = iw * scale
    img.drawHeight = ih * scale
    return [img, Paragraph(caption, styles["caption"])]


def sector_cards(product: dict, styles, col_w):
    """2×2 application cards as a simple table of Paragraphs (no KeepTogether)."""
    cells = []
    row: list = []
    for title, key in SECTORS:
        text = (
            f"<b>{title}</b><br/><font size='8'>{product.get(key, '')}</font>"
        )
        row.append(Paragraph(text, styles["sector_body"]))
        if len(row) == 2:
            cells.append(row)
            row = []
    if row:
        row.append(Paragraph("", styles["sector_body"]))
        cells.append(row)

    table = Table(cells, colWidths=[col_w, col_w])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), TEAL_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.4, TEAL),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def day_night_note(product: dict) -> str:
    name = product["product_name"]
    kind = product["product_kind"]
    if name in SOLAR_DEPENDENT_CHANNELS:
        return (
            "Day/night: <b>daylight only</b>. This solar channel is blank or unavailable "
            "for nighttime timeslots — that is expected, not a processing error."
        )
    solar_comps = {
        "natural_color",
        "natural_color_nocorr",
        "natural_color_raw",
        "natural_enh",
        "overview",
        "overview_raw",
        "day_microphysics",
        "day_microphysics_winter",
        "day_severe_storms",
        "day_severe_storms_tropical",
        "snow",
        "green_snow",
        "cloudtop_daytime",
        "natural_with_night_fog",
        "natural_color_raw_with_night_ir",
        "cloud_convective_storms",
        "dust_cloud",
    }
    if name in solar_comps:
        return (
            "Day/night: <b>primarily daytime</b>. Solar-reflectance ingredients mean this "
            "composite is typically unavailable or unusable at night."
        )
    if kind == "channel":
        return "Day/night: <b>day and night</b>. Thermal / water-vapour emission works around the clock."
    return (
        "Day/night: usually available <b>day and night</b> (IR/WV-based recipe). "
        "Always confirm availability status in the app gallery."
    )


# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------


def build_interpretation_report(products: list[dict], styles):
    doc = SimpleDocTemplate(
        str(OUT_REPORT),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title="MSG HRIT Product Interpretation & Applications Report",
        author="MSG HRIT Terrestrial Archive Explorer",
    )
    story = []
    story += cover_block(
        styles,
        "MSG SEVIRI Product Interpretation\n& Sector Applications Report",
        "Channels · Composites · Agriculture · Aviation · Natural Resources · Disaster Response",
        [
            "Plain-language interpretation of every SEVIRI channel and composite in the archive explorer",
            "Sector applications for Agriculture, Aviation, Natural Resource Monitoring, and Natural Disaster Monitoring",
            "Example full-disk imagery from the local curated sample archive",
            f"{len(products)} meteorological products documented",
        ],
    )

    # intro
    story.append(Paragraph("1. Purpose of this report", styles["h1"]))
    story.append(
        Paragraph(
            "This report explains how to interpret each meteorological product generated from "
            "MSG-2 / SEVIRI native (.nat) files in the HRIT Terrestrial Archive, and how each "
            "product supports four operational sectors. It is the long-form companion to the "
            "in-app product reference glossary and the two-page user guide PDF in this folder.",
            styles["body"],
        )
    )
    story.append(Paragraph("2. How to use the products", styles["h1"]))
    story.append(
        Paragraph(
            "Browse the explorer by date → timeslot (daytime / twilight / nighttime sample roles) → "
            "product gallery. Read the image together with the spectral band and the four sector notes. "
            "Solar channels and some RGB composites are legitimately unavailable at night.",
            styles["body"],
        )
    )
    story.append(PageBreak())

    # TOC
    story.append(Paragraph("3. Product index", styles["h1"]))
    for i, p in enumerate(products, 1):
        kind = "Channel" if p["product_kind"] == "channel" else "Composite"
        story.append(
            Paragraph(
                f"{i:02d}. <b>{product_label(p['product_name'])}</b> "
                f"<font color='#5a6a75'>({kind} · {p['product_name']})</font>",
                styles["toc"],
            )
        )
    story.append(PageBreak())

    usable_w = PAGE_W - 2 * MARGIN
    for idx, p in enumerate(products, 1):
        name = p["product_name"]
        label = product_label(name)
        kind = "SEVIRI Channel" if p["product_kind"] == "channel" else "RGB Composite"

        header = Table(
            [[Paragraph(f"{idx:02d}  ·  {label}", styles["cover_title"])]],
            colWidths=[usable_w],
        )
        header.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ]
            )
        )
        bar = Table([[""]], colWidths=[usable_w], rowHeights=[3])
        bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEAL)]))

        story.append(header)
        story.append(bar)
        story.append(Spacer(1, 4 * mm))
        story.append(
            Paragraph(
                f"<b>{kind}</b>  ·  ID: <b>{name}</b>  ·  "
                f"Band: {p['wavelength_or_spectral_band']}  ·  "
                f"Resolution: {p['approximate_resolution']}",
                styles["meta"],
            )
        )
        story.append(Paragraph("Interpretation", styles["h2"]))
        story.append(Paragraph(p["plain_language_description"], styles["body"]))
        story.append(Paragraph(day_night_note(p), styles["small"]))

        img_path = find_product_image(name)
        story += image_flowable(
            img_path,
            max_w=usable_w,
            max_h=68 * mm,
            styles=styles,
            caption=f"Figure — {label} ({name}). Sample from local MSG HRIT archive processing.",
        )

        story.append(Paragraph("Sector applications", styles["h2"]))
        story.append(sector_cards(p, styles, (usable_w - 4) / 2))
        story.append(PageBreak())

    doc.build(story, onFirstPage=header_footer_factory("Interpretation & Applications Report"),
              onLaterPages=header_footer_factory("Interpretation & Applications Report"))
    print(f"Wrote {OUT_REPORT}")


# ---------------------------------------------------------------------------
# USER GUIDE — exactly 2 pages per product
# ---------------------------------------------------------------------------


def build_user_guide(products: list[dict], styles):
    """
    Two fixed pages per product:
      Page A — identity, how to read, large image
      Page B — four sector applications + quick tips
    """
    usable_w = PAGE_W - 2 * MARGIN

    doc = SimpleDocTemplate(
        str(OUT_GUIDE),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title="MSG HRIT Product User Guide (Two-Pager)",
        author="MSG HRIT Terrestrial Archive Explorer",
    )

    story = []
    story += cover_block(
        styles,
        "MSG SEVIRI Product User Guide\nTwo Pages per Product",
        "Quick-reference sheets for every channel and composite in the archive explorer",
        [
            "Page 1 of each sheet: what the product is, spectral identity, and an example image",
            "Page 2 of each sheet: Agriculture · Aviation · Natural Resources · Disaster applications + tips",
            f"{len(products)} products × 2 pages = {len(products) * 2} guide pages (plus this cover)",
            "Designed for printing or on-screen briefing alongside the Interpretation Report",
        ],
    )

    # mini index (compact)
    story.append(Paragraph("How to use these sheets", styles["h1"]))
    story.append(
        Paragraph(
            "Each product occupies <b>exactly two pages</b>. Keep the pair together when printing "
            "(double-sided if possible). In the web app, open the matching timeslot gallery tile for "
            "the live image and the same glossary text.",
            styles["body"],
        )
    )
    story.append(Paragraph("Product order", styles["h2"]))
    cols = [[], [], []]
    for i, p in enumerate(products):
        cols[i % 3].append(
            Paragraph(
                f"{i+1:02d}. {product_label(p['product_name'])}",
                styles["small"],
            )
        )
    # pad
    m = max(len(c) for c in cols)
    for c in cols:
        while len(c) < m:
            c.append(Paragraph("", styles["small"]))
    idx_table = Table(
        [[cols[0][r], cols[1][r], cols[2][r]] for r in range(m)],
        colWidths=[usable_w / 3.0] * 3,
    )
    idx_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(idx_table)
    story.append(PageBreak())

    for idx, p in enumerate(products, 1):
        name = p["product_name"]
        label = product_label(name)
        kind = "Channel" if p["product_kind"] == "channel" else "Composite"

        # ===== PAGE 1 =====
        kicker = Paragraph(
            f"USER GUIDE  ·  SHEET {idx:02d} / {len(products):02d}  ·  PAGE 1 OF 2",
            styles["guide_kicker"],
        )
        title = Paragraph(label, styles["guide_title"])
        meta = Paragraph(
            f"<b>{kind}</b> &nbsp;|&nbsp; Product ID: <b>{name}</b><br/>"
            f"Spectral / recipe: {p['wavelength_or_spectral_band']}<br/>"
            f"Approximate resolution: {p['approximate_resolution']}",
            styles["meta"],
        )

        strip = Table(
            [[kicker], [title], [meta]],
            colWidths=[usable_w],
        )
        strip.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
                    ("BOX", (0, 0), (-1, -1), 0.8, TEAL),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (0, 0), 8),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
                    ("TOPPADDING", (0, 1), (-1, -1), 2),
                ]
            )
        )
        story.append(strip)
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("What this product shows", styles["h2"]))
        story.append(Paragraph(p["plain_language_description"], styles["body"]))
        story.append(Paragraph(day_night_note(p), styles["small"]))
        story.append(Paragraph("Example image", styles["h2"]))
        story += image_flowable(
            find_product_image(name),
            max_w=usable_w,
            max_h=95 * mm,
            styles=styles,
            caption=f"{label} — example from MSG HRIT sample processing (prefer daytime 09:00).",
        )
        story.append(PageBreak())

        # ===== PAGE 2 =====
        kicker2 = Paragraph(
            f"USER GUIDE  ·  SHEET {idx:02d} / {len(products):02d}  ·  PAGE 2 OF 2  ·  {label}",
            styles["guide_kicker"],
        )
        story.append(kicker2)
        story.append(Paragraph("Applications by sector", styles["h1"]))
        story.append(sector_cards(p, styles, (usable_w - 4) / 2))
        story.append(Spacer(1, 4 * mm))

        tips = [
            f"<b>In the app:</b> open Browse → pick a date → open the {name} tile in the timeslot gallery.",
            "<b>Compare roles:</b> use daytime / twilight / nighttime siblings to see solar vs thermal behaviour.",
            "<b>Combine products:</b> pair window IR (IR_108) with dust/ash RGBs or WV channels for context.",
            "<b>Trust night blanks:</b> solar channels marked unavailable at night are physically empty, not failed jobs.",
        ]
        tip_rows = [[Paragraph("Quick operating tips", styles["sector_title"])]]
        for t in tips:
            tip_rows.append([Paragraph(f"• {t}", styles["sector_body"])])
        tip_box = Table(tip_rows, colWidths=[usable_w])
        tip_box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
                    ("BOX", (0, 0), (-1, -1), 0.6, SLATE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(tip_box)
        story.append(Spacer(1, 4 * mm))
        story.append(
            Paragraph(
                f"End of sheet {idx:02d} — {label}. Continue to the next product sheet, or return to the "
                "Interpretation & Applications Report for longer narrative context.",
                styles["small"],
            )
        )
        if idx < len(products):
            story.append(PageBreak())

    doc.build(
        story,
        onFirstPage=header_footer_factory("Product User Guide (Two-Pager)"),
        onLaterPages=header_footer_factory("Product User Guide (Two-Pager)"),
    )
    print(f"Wrote {OUT_GUIDE}")


def main():
    styles = make_styles()
    products = all_products()
    print(f"Products: {len(products)} (channels={sum(1 for p in products if p['product_kind']=='channel')}, "
          f"composites={sum(1 for p in products if p['product_kind']=='composite')})")
    build_interpretation_report(products, styles)
    build_user_guide(products, styles)
    readme = DOCS_DIR / "README.md"
    readme.write_text(
        """# MSG HRIT — Documentation PDFs

Generated from the in-app product reference glossary and local sample imagery.

| File | Description |
|------|-------------|
| `MSG_HRIT_Product_Interpretation_Applications_Report.pdf` | Full interpretation report for every SEVIRI channel and composite, with sector applications (Agriculture, Aviation, Natural Resource Monitoring, Natural Disaster Monitoring) and example images. |
| `MSG_HRIT_Product_User_Guide_Two_Pager.pdf` | Printable **two-page sheet per product** (identity + image on page 1; four sector applications + tips on page 2). |

## Regenerate

```bash
backend\\.venv\\Scripts\\python docs\\generate_product_pdfs.py
```

Requires `reportlab` and `pillow` in the backend virtualenv. Sample images are read from `data/processed/` (daytime `2026-06-22/09-00`, night fallback `20-00`).
""",
        encoding="utf-8",
    )
    print(f"Wrote {readme}")


if __name__ == "__main__":
    main()
