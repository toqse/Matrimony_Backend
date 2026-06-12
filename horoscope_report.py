"""
Kerala-style Horoscope Matching Report — 3-page A4 PDF generator (ReportLab).

The report is bilingual: English for all headings/labels, Malayalam script only
for porutham names and grahanil (rasi chart) content. Everything is drawn with
ReportLab canvas primitives (no images), so it renders identically in the admin
panel and on the user site.

Public API
----------
build_horoscope_report_pdf(report) -> bytes
    Render the 3-page report from a plain dict (see SAMPLE_REPORT for the shape).

placements_from_pr_rasi(pr_rasi) -> dict[(row, col), list[str]]
    Convert an 11-char EXE ``pr_rasi`` string (A-L per planet) into South-Indian
    chart placements keyed by grid cell, ready for the chart renderer.

Run directly to emit a sample PDF:
    python horoscope_report.py [output.pdf]
"""
from __future__ import annotations

import os
import sys
from io import BytesIO

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# --------------------------------------------------------------------------- #
# Color palette
# --------------------------------------------------------------------------- #
DARK_MAROON = HexColor("#4A0808")
MAROON = HexColor("#7B1A1A")
GOLD = HexColor("#C9A84C")
LIGHT_GOLD = HexColor("#FBF3E0")
BG = HexColor("#FDF9F3")
MID_GREY = HexColor("#D4C9B8")
GREEN_MATCH = HexColor("#2E7D32")
RED_NO = HexColor("#C62828")
TEXT_GREY = HexColor("#7A7167")

# --------------------------------------------------------------------------- #
# Fonts — Malayalam from Noto, everything else Helvetica
# --------------------------------------------------------------------------- #
MAL = "Mal"
MAL_BOLD = "MalBold"

_FONT_SEARCH_DIRS = (
    "/usr/share/fonts/truetype/noto/",
    "/usr/share/fonts/truetype/smc/",
    "/usr/share/fonts/opentype/noto/",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"),
    r"C:\Windows\Fonts",
)


def _find_font(*candidates: str) -> str | None:
    for directory in _FONT_SEARCH_DIRS:
        for name in candidates:
            path = os.path.join(directory, name)
            if os.path.exists(path):
                return path
    return None


def register_fonts() -> bool:
    """Register Noto Sans Malayalam as ``Mal`` / ``MalBold``.

    Returns True when real Malayalam glyphs are available. When the TTFs cannot
    be found (e.g. a bare Windows dev box) the aliases fall back to Helvetica so
    the script never crashes; Malayalam text then renders as boxes locally but is
    correct inside the Docker image that ships ``fonts-noto-core``.
    """
    regular = _find_font(
        "NotoSansMalayalam-Regular.ttf",
        "NotoSansMalayalam_Regular.ttf",
        "Rachana-Regular.ttf",
        "Meera.ttf",
    )
    bold = _find_font(
        "NotoSansMalayalam-Bold.ttf",
        "NotoSansMalayalam_Bold.ttf",
        "Rachana-Bold.ttf",
    )
    if not regular:
        pdfmetrics.registerFontFamily(MAL, normal="Helvetica", bold="Helvetica-Bold")
        _alias_to_helvetica()
        return False
    try:
        pdfmetrics.registerFont(TTFont(MAL, regular))
        pdfmetrics.registerFont(TTFont(MAL_BOLD, bold or regular))
        return True
    except Exception:
        _alias_to_helvetica()
        return False


def _alias_to_helvetica() -> None:
    # Map the Malayalam aliases onto Helvetica so drawString calls keep working.
    from reportlab.pdfbase.pdfmetrics import standardFonts  # noqa: F401

    global MAL, MAL_BOLD
    MAL = "Helvetica"
    MAL_BOLD = "Helvetica-Bold"


# --------------------------------------------------------------------------- #
# Static data: Malayalam names, chart layout, planet abbreviations
# --------------------------------------------------------------------------- #
PORUTHAM_MAL = {
    "Dinam": "ദിനം", "Ganam": "ഗണം", "Mahendram": "മഹേന്ദ്രം",
    "Sthree Deergham": "സ്ത്രീദീർഘം", "Yoni": "യോനി", "Rasi": "രാശി",
    "Rasyadhipathi": "രാശ്യാധിപതി", "Vasyam": "വശ്യം",
    "Rajju": "രജ്ജു", "Vedha": "വേദ",
}

# (row, col) -> (house_number, malayalam_rasi_name) for the 12 outer cells.
RASI_GRID = {
    (0, 0): (12, "മീനം"), (0, 1): (1, "മേടം"), (0, 2): (2, "ഇടവം"), (0, 3): (3, "മിഥുനം"),
    (1, 0): (11, "കുംഭം"), (1, 3): (4, "കർക്കടകം"),
    (2, 0): (10, "മകരം"), (2, 3): (5, "ചിങ്ങം"),
    (3, 0): (9, "ധനു"), (3, 1): (8, "വൃശ്ചികം"), (3, 2): (7, "തുലാം"), (3, 3): (6, "കന്നി"),
}

PLANET_MAL = {
    "Gu": "ഗു", "Ra": "രാ", "Shu": "ശു", "Bu": "ബു", "Sha": "ശ",
    "Ku": "കു", "Cha": "ച", "Ke": "കേ", "La": "ല", "Ma": "മ",
    "Su": "ര",  # Sun — not in the original sample, used for live EXE charts.
}

# Legacy Windows EXE chart uses traditional Kerala alternate graha names instead
# of the plain abbreviations above. Applied as a single lookup per glyph so the
# remaps never chain (e.g. Saturn ശ→മ must not then become Maandi's മ→മാ):
#   കേതു → ശിഖി (ശി), ശനി → മന്ദൻ (മ), മാന്ദി → മാ, രാഹു → സ
LEGACY_PLANET_DISPLAY = {
    "കേ": "ശി",
    "ശ": "മ",
    "മ": "മാ",
    "രാ": "സ",
}


def planet_glyph(key: str) -> str:
    """Return the legacy-EXE Malayalam glyph for a planet abbreviation key."""
    base = PLANET_MAL.get(key, key)
    return LEGACY_PLANET_DISPLAY.get(base, base)

# EXE pr_rasi position (1-based) -> planet abbreviation key.
_PR_RASI_PLANET_ORDER = {
    1: "La", 2: "Su", 3: "Cha", 4: "Ku", 5: "Bu", 6: "Gu",
    7: "Shu", 8: "Sha", 9: "Ra", 10: "Ke", 11: "Ma",
}
# Zodiac sign number (1-12) -> grid cell.
_SIGN_TO_CELL = {num: cell for cell, (num, _name) in RASI_GRID.items()}


def placements_from_pr_rasi(pr_rasi: str) -> dict:
    """Map an 11-char EXE ``pr_rasi`` string to chart-cell placements.

    Each character A-L is a zodiac sign (1-12); position is the planet. Returns
    ``{(row, col): [planet_keys]}`` suitable for ``person['placements']``.
    """
    placements: dict = {}
    if not pr_rasi:
        return placements
    for idx, ch in enumerate(pr_rasi.strip(), start=1):
        key = _PR_RASI_PLANET_ORDER.get(idx)
        if not key:
            continue
        ch = ch.upper()
        if not ("A" <= ch <= "L"):
            continue
        sign = ord(ch) - ord("A") + 1
        cell = _SIGN_TO_CELL.get(sign)
        if cell is None:
            continue
        placements.setdefault(cell, []).append(key)
    return placements


# --------------------------------------------------------------------------- #
# Page geometry
# --------------------------------------------------------------------------- #
PAGE_W, PAGE_H = A4
MARGIN = 40.0
CONTENT_X = MARGIN
CONTENT_W = PAGE_W - 2 * MARGIN
HEADER_H = 96.0
FOOTER_Y = 34.0


# --------------------------------------------------------------------------- #
# Low-level drawing helpers
# --------------------------------------------------------------------------- #
def _centred(c: canvas.Canvas, x: float, y: float, text: str, font: str, size: float, color) -> None:
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawCentredString(x, y, text)


def _left(c: canvas.Canvas, x: float, y: float, text: str, font: str, size: float, color) -> None:
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawString(x, y, text)


def _star(c: canvas.Canvas, cx: float, cy: float, r: float, color) -> None:
    """Small filled 4-point star used as a brand flourish."""
    c.setFillColor(color)
    p = c.beginPath()
    pts = [
        (cx, cy + r), (cx + r * 0.28, cy + r * 0.28), (cx + r, cy),
        (cx + r * 0.28, cy - r * 0.28), (cx, cy - r), (cx - r * 0.28, cy - r * 0.28),
        (cx - r, cy), (cx - r * 0.28, cy + r * 0.28),
    ]
    p.moveTo(*pts[0])
    for pt in pts[1:]:
        p.lineTo(*pt)
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def _check(c: canvas.Canvas, cx: float, cy: float, s: float, color) -> None:
    """Draw a check mark centred at (cx, cy), drawn as vector strokes."""
    c.setStrokeColor(color)
    c.setLineWidth(1.5)
    c.setLineCap(1)
    c.line(cx - s * 0.5, cy, cx - s * 0.1, cy - s * 0.45)
    c.line(cx - s * 0.1, cy - s * 0.45, cx + s * 0.55, cy + s * 0.55)


def _cross(c: canvas.Canvas, cx: float, cy: float, s: float, color) -> None:
    """Draw an X mark centred at (cx, cy), drawn as vector strokes."""
    c.setStrokeColor(color)
    c.setLineWidth(1.5)
    c.setLineCap(1)
    c.line(cx - s * 0.45, cy - s * 0.45, cx + s * 0.45, cy + s * 0.45)
    c.line(cx - s * 0.45, cy + s * 0.45, cx + s * 0.45, cy - s * 0.45)


# --------------------------------------------------------------------------- #
# Shared header & footer
# --------------------------------------------------------------------------- #
def _draw_header(c: canvas.Canvas, report: dict) -> float:
    top = PAGE_H - MARGIN
    y0 = top - HEADER_H
    c.setFillColor(DARK_MAROON)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.5)
    c.roundRect(CONTENT_X, y0, CONTENT_W, HEADER_H, 10, stroke=1, fill=1)

    cx = PAGE_W / 2
    brand = "AISWARYA  MATRIMONIALS"
    _centred(c, cx, top - 22, brand, "Helvetica-Bold", 9, GOLD)
    bw = c.stringWidth(brand, "Helvetica-Bold", 9)
    _star(c, cx - bw / 2 - 12, top - 19, 4, GOLD)
    _star(c, cx + bw / 2 + 12, top - 19, 4, GOLD)

    _centred(c, cx, top - 46, "Horoscope Matching Report", "Helvetica-Bold", 18, white)
    _centred(c, cx, top - 66, report.get("couple", ""), "Helvetica", 11, LIGHT_GOLD)
    _centred(
        c, cx, top - 82,
        f"Report generated: {report.get('date', '')}",
        "Helvetica", 8.5, GOLD,
    )
    return y0


def _draw_footer(c: canvas.Canvas, page_num: int, total: int = 3) -> None:
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.6)
    c.line(CONTENT_X, FOOTER_Y + 12, CONTENT_X + CONTENT_W, FOOTER_Y + 12)
    _centred(
        c, PAGE_W / 2, FOOTER_Y,
        "Generated by Aiswarya Matrimonials \u2022 Confidential",
        "Helvetica", 8, TEXT_GREY,
    )
    _left(c, CONTENT_X, FOOTER_Y, f"Page {page_num} of {total}", "Helvetica", 8, TEXT_GREY)


def _paint_background(c: canvas.Canvas) -> None:
    c.setFillColor(BG)
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)


# --------------------------------------------------------------------------- #
# Page 1 — Match summary
# --------------------------------------------------------------------------- #
def _draw_score_card(c: canvas.Canvas, report: dict, top_y: float) -> float:
    score = report.get("score", 0)
    max_score = report.get("max", 10)
    overall = report.get("overall", "")

    card_h = 96.0
    card_y = top_y - card_h
    c.setFillColor(white)
    c.setStrokeColor(MID_GREY)
    c.setLineWidth(1)
    c.roundRect(CONTENT_X, card_y, CONTENT_W, card_h, 10, stroke=1, fill=1)

    # Circular score badge on the left.
    r = 34.0
    badge_cx = CONTENT_X + 28 + r
    badge_cy = card_y + card_h / 2
    c.setFillColor(MAROON)
    c.setStrokeColor(GOLD)
    c.setLineWidth(2)
    c.circle(badge_cx, badge_cy, r, stroke=1, fill=1)
    _centred(c, badge_cx, badge_cy + 1, str(score), "Helvetica-Bold", 26, GOLD)
    _centred(c, badge_cx, badge_cy - 18, f"/ {max_score}", "Helvetica-Bold", 11, GOLD)

    # Text + progress bar on the right.
    text_x = badge_cx + r + 26
    _left(c, text_x, badge_cy + 22, f"Overall Match: {overall}", "Helvetica-Bold", 14, DARK_MAROON)
    _left(
        c, text_x, badge_cy + 6,
        f"{score} out of {max_score} Poruthams matched",
        "Helvetica", 10, TEXT_GREY,
    )

    bar_x = text_x
    bar_w = CONTENT_X + CONTENT_W - bar_x - 24
    bar_y = badge_cy - 20
    bar_h = 11.0
    pct = (score / max_score) if max_score else 0
    c.setFillColor(MID_GREY)
    c.roundRect(bar_x, bar_y, bar_w, bar_h, bar_h / 2, stroke=0, fill=1)
    if pct > 0:
        c.setFillColor(GOLD)
        c.roundRect(bar_x, bar_y, max(bar_h, bar_w * pct), bar_h, bar_h / 2, stroke=0, fill=1)
    _left(c, bar_x + bar_w - 26, bar_y + 2, f"{int(round(pct * 100))}%", "Helvetica-Bold", 8, DARK_MAROON)

    return card_y


def _status_badge(c: canvas.Canvas, cx: float, cy: float, matched: bool) -> None:
    label = "Match" if matched else "No"
    color = GREEN_MATCH if matched else RED_NO
    bw, bh = 70.0, 17.0
    bx = cx - bw / 2
    by = cy - bh / 2
    c.setFillColor(color)
    c.roundRect(bx, by, bw, bh, bh / 2, stroke=0, fill=1)
    mark_x = bx + 15
    if matched:
        _check(c, mark_x, cy, 8, white)
    else:
        _cross(c, mark_x, cy, 8, white)
    _left(c, mark_x + 12, cy - 3.5, label, "Helvetica-Bold", 9, white)


def _draw_porutham_table(c: canvas.Canvas, report: dict, top_y: float) -> None:
    rows = report.get("rows", [])

    _left(c, CONTENT_X, top_y - 4, "Porutham Details", "Helvetica-Bold", 13, DARK_MAROON)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.5)
    c.line(CONTENT_X, top_y - 9, CONTENT_X + 120, top_y - 9)

    table_top = top_y - 20
    col_status_w = 100.0
    col_porutham_w = 150.0
    col_sig_w = CONTENT_W - col_porutham_w - col_status_w

    x_porutham = CONTENT_X
    x_sig = CONTENT_X + col_porutham_w
    x_status = CONTENT_X + col_porutham_w + col_sig_w

    head_h = 22.0
    row_h = 33.0
    summary_h = 26.0

    # Header row.
    c.setFillColor(DARK_MAROON)
    c.rect(CONTENT_X, table_top - head_h, CONTENT_W, head_h, stroke=0, fill=1)
    _left(c, x_porutham + 10, table_top - 15, "Porutham", "Helvetica-Bold", 9.5, white)
    _left(c, x_sig + 10, table_top - 15, "Significance", "Helvetica-Bold", 9.5, white)
    _centred(c, x_status + col_status_w / 2, table_top - 15, "Status", "Helvetica-Bold", 9.5, white)

    y = table_top - head_h
    for i, row in enumerate(rows):
        ry = y - row_h
        shade = LIGHT_GOLD if i % 2 == 0 else white
        c.setFillColor(shade)
        c.rect(CONTENT_X, ry, CONTENT_W, row_h, stroke=0, fill=1)

        eng = row.get("english", "")
        mal = PORUTHAM_MAL.get(eng, row.get("malayalam", ""))
        _left(c, x_porutham + 10, ry + row_h - 14, eng, "Helvetica-Bold", 10, DARK_MAROON)
        _left(c, x_porutham + 10, ry + 8, mal, MAL, 8.5, MAROON)

        _left(c, x_sig + 10, ry + row_h / 2 - 3.5, row.get("significance", ""), "Helvetica", 9, TEXT_GREY)

        _status_badge(c, x_status + col_status_w / 2, ry + row_h / 2, bool(row.get("matched")))
        y = ry

    # Column separators over the data rows.
    c.setStrokeColor(MID_GREY)
    c.setLineWidth(0.5)
    c.line(x_sig, table_top - head_h, x_sig, y)
    c.line(x_status, table_top - head_h, x_status, y)

    # Summary footer row.
    sy = y - summary_h
    c.setFillColor(DARK_MAROON)
    c.rect(CONTENT_X, sy, CONTENT_W, summary_h, stroke=0, fill=1)
    matched = report.get("matched", sum(1 for r in rows if r.get("matched")))
    unmatched = report.get("unmatched", len(rows) - matched)
    mid = sy + summary_h / 2
    _check(c, CONTENT_X + 24, mid, 9, GOLD)
    _left(c, CONTENT_X + 36, mid - 4, f"Matched: {matched}", "Helvetica-Bold", 11, white)
    _cross(c, CONTENT_X + CONTENT_W / 2 + 20, mid, 9, GOLD)
    _left(c, CONTENT_X + CONTENT_W / 2 + 34, mid - 4, f"Unmatched: {unmatched}", "Helvetica-Bold", 11, white)


def _render_page1(c: canvas.Canvas, report: dict, total_pages: int = 3) -> None:
    _paint_background(c)
    header_bottom = _draw_header(c, report)
    score_bottom = _draw_score_card(c, report, header_bottom - 18)
    _draw_porutham_table(c, report, score_bottom - 22)
    _draw_footer(c, 1, total_pages)


# --------------------------------------------------------------------------- #
# Pages 2 & 3 — Bride / Groom
# --------------------------------------------------------------------------- #
def _draw_role_banner(c: canvas.Canvas, role: str, top_y: float) -> float:
    h = 26.0
    y0 = top_y - h
    c.setFillColor(MAROON)
    c.rect(CONTENT_X, y0, CONTENT_W, h, stroke=0, fill=1)
    _left(c, CONTENT_X + 14, y0 + 8, role.upper(), "Helvetica-Bold", 12, white)
    return y0


def _draw_name_card(c: canvas.Canvas, person: dict, top_y: float) -> float:
    h = 50.0
    y0 = top_y - h
    c.setFillColor(LIGHT_GOLD)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.roundRect(CONTENT_X, y0, CONTENT_W, h, 8, stroke=1, fill=1)
    _left(c, CONTENT_X + 16, y0 + 26, person.get("name", ""), "Helvetica-Bold", 18, DARK_MAROON)
    _left(c, CONTENT_X + 16, y0 + 10, person.get("am_id", ""), "Helvetica", 10, MAROON)
    return y0


def _draw_info_grid(c: canvas.Canvas, person: dict, top_y: float) -> float:
    fields = [
        ("NAKSHATRA", person.get("nakshatra", "")),
        ("PADAM", str(person.get("padam", ""))),
        ("RASI", person.get("rasi", "")),
        ("LAGNAM", person.get("lagnam", "")),
        ("DASA BALANCE", person.get("dasa", "")),
        ("LORD", person.get("lord", "")),
    ]
    cols, rows = 3, 2
    gap = 10.0
    box_w = (CONTENT_W - gap * (cols - 1)) / cols
    box_h = 40.0
    grid_h = rows * box_h + gap * (rows - 1)
    for idx, (label, value) in enumerate(fields):
        r = idx // cols
        col = idx % cols
        bx = CONTENT_X + col * (box_w + gap)
        by = top_y - (r + 1) * box_h - r * gap
        c.setFillColor(white)
        c.setStrokeColor(MID_GREY)
        c.setLineWidth(1)
        c.roundRect(bx, by, box_w, box_h, 6, stroke=1, fill=1)
        _left(c, bx + 10, by + box_h - 15, label, "Helvetica", 7.5, TEXT_GREY)
        _left(c, bx + 10, by + 9, str(value) or "\u2014", "Helvetica-Bold", 12, DARK_MAROON)
    return top_y - grid_h


def _draw_section_title(c: canvas.Canvas, text: str, top_y: float) -> float:
    _left(c, CONTENT_X, top_y - 4, text, "Helvetica-Bold", 13, DARK_MAROON)
    tw = c.stringWidth(text, "Helvetica-Bold", 13)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.5)
    c.line(CONTENT_X, top_y - 9, CONTENT_X + tw, top_y - 9)
    return top_y - 16


def _draw_single_chart(
    c: canvas.Canvas,
    placements: dict,
    center_label: str,
    chart_x: float,
    chart_top: float,
    size: float,
    *,
    fs_house: float,
    fs_rasi: float,
    fs_planet: float,
    fs_center: float,
) -> None:
    """Draw one South-Indian 4x4 chart at (chart_x, chart_top) with side ``size``."""
    cell = size / 4
    chart_bottom = chart_top - size

    # Outer border.
    c.setStrokeColor(MAROON)
    c.setLineWidth(2)
    c.roundRect(chart_x, chart_bottom, size, size, 5, stroke=1, fill=0)

    # Inner 2x2 centre block (rows 1-2, cols 1-2) — labelled with the chart name.
    inner_x = chart_x + cell
    inner_y = chart_bottom + cell
    inner_w = cell * 2
    c.setFillColor(LIGHT_GOLD)
    c.setStrokeColor(MAROON)
    c.setLineWidth(1)
    c.rect(inner_x, inner_y, inner_w, inner_w, stroke=1, fill=1)
    _centred(
        c, inner_x + inner_w / 2, inner_y + inner_w / 2 - fs_center * 0.35,
        center_label, MAL_BOLD, fs_center, DARK_MAROON,
    )

    # Outer cells: house number, Malayalam rasi name, planet glyphs.
    c.setLineWidth(0.6)
    for (row, col), (house, rasi_name) in RASI_GRID.items():
        x0 = chart_x + col * cell
        y_top = chart_top - row * cell
        y0 = y_top - cell
        c.setStrokeColor(MID_GREY)
        c.rect(x0, y0, cell, cell, stroke=1, fill=0)

        _left(c, x0 + 3, y_top - fs_house - 3, str(house), "Helvetica-Bold", fs_house, TEXT_GREY)
        _centred(c, x0 + cell / 2, y_top - fs_rasi - 8, rasi_name, MAL, fs_rasi, DARK_MAROON)

        planets = placements.get((row, col), [])
        if planets:
            glyphs = " ".join(planet_glyph(p) for p in planets)
            _centred(c, x0 + cell / 2, y0 + cell * 0.22, glyphs, MAL_BOLD, fs_planet, MAROON)


# (English title, Malayalam centre label, person key) for the three charts.
_PERSON_CHARTS = (
    ("Rasi Chart (Grahanil)", "\u0d30\u0d3e\u0d36\u0d3f", "placements"),
    ("Amsakam Chart (Navamsam)", "\u0d05\u0d02\u0d36\u0d15\u0d02", "amsa_placements"),
    ("Bhavam Chart", "\u0d2d\u0d3e\u0d35\u0d02", "bhava_placements"),
)

# Each chart is drawn large and stacked vertically so the cell text never
# overflows. Three big charts cannot share a page, so the person section spans
# two pages: info + Rasi, then Amsakam + Bhavam.
CHART_SIZE = 275.0
CHART_TITLE_H = 18.0
CHART_GAP = 16.0


def _draw_titled_chart(
    c: canvas.Canvas, chart_def: tuple, person: dict, top_y: float, size: float
) -> float:
    """Draw a centred, titled chart; return the y just below it."""
    title, center_mal, key = chart_def
    chart_x = CONTENT_X + (CONTENT_W - size) / 2
    _centred(c, chart_x + size / 2, top_y - 13, title, "Helvetica-Bold", 11, DARK_MAROON)
    _draw_single_chart(
        c,
        person.get(key, {}),
        center_mal,
        chart_x,
        top_y - CHART_TITLE_H,
        size,
        fs_house=7,
        fs_rasi=7,
        fs_planet=11,
        fs_center=13,
    )
    return top_y - CHART_TITLE_H - size


def _render_person_pages(
    c: canvas.Canvas, report: dict, person: dict, start_page: int, total_pages: int
) -> None:
    """Render a person's two pages: info + Rasi, then Amsakam + Bhavam."""
    role = person.get("role", "")

    # Page A — member details + Rasi chart (vertically centred in free space).
    _paint_background(c)
    y = _draw_header(c, report)
    y = _draw_role_banner(c, role, y - 16)
    y = _draw_name_card(c, person, y - 12)
    y = _draw_info_grid(c, person, y - 14)
    y = _draw_section_title(c, "Horoscope Charts (Grahanil)", y - 16)
    block_h = CHART_TITLE_H + CHART_SIZE
    avail = (y - 8) - (FOOTER_Y + 22)
    rasi_top = (y - 8) - max(0.0, (avail - block_h) / 2)
    _draw_titled_chart(c, _PERSON_CHARTS[0], person, rasi_top, CHART_SIZE)
    _draw_footer(c, start_page, total_pages)
    c.showPage()

    # Page B — Amsakam + Bhavam charts stacked.
    _paint_background(c)
    y = _draw_header(c, report)
    y = _draw_section_title(c, f"{role.title()} — Horoscope Charts (continued)", y - 16)
    y -= 6
    for chart_def in _PERSON_CHARTS[1:]:
        y = _draw_titled_chart(c, chart_def, person, y, CHART_SIZE) - CHART_GAP
    _draw_footer(c, start_page + 1, total_pages)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def build_horoscope_report_pdf(report: dict) -> bytes:
    """Render the horoscope matching report and return PDF bytes.

    Layout: page 1 = match summary; the bride and groom each take two pages
    (member details + Rasi, then Amsakam + Bhavam) → 5 pages total.
    """
    register_fonts()
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle("Horoscope Matching Report")

    total_pages = 5
    _render_page1(c, report, total_pages)
    c.showPage()
    _render_person_pages(c, report, report["bride"], 2, total_pages)
    c.showPage()
    _render_person_pages(c, report, report["groom"], 4, total_pages)
    c.showPage()

    c.save()
    buffer.seek(0)
    return buffer.read()


# --------------------------------------------------------------------------- #
# Sample data (matches horoscope_matching_report_v3.pdf)
# --------------------------------------------------------------------------- #
_SAMPLE_ROWS = [
    ("Dinam", "Health & longevity", False),
    ("Ganam", "Temperament & nature", True),
    ("Mahendram", "Prosperity & progeny", False),
    ("Sthree Deergham", "Long married life", True),
    ("Yoni", "Physical compatibility", False),
    ("Rasi", "Mental harmony", True),
    ("Rasyadhipathi", "Ruling lords match", False),
    ("Vasyam", "Mutual attraction", False),
    ("Rajju", "Life span protection", True),
    ("Vedha", "Absence of affliction", True),
]

SAMPLE_REPORT = {
    "couple": "anju & arun as",
    "date": "12-06-2026 09:33",
    "score": 5,
    "max": 10,
    "overall": "Average",
    "matched": 5,
    "unmatched": 5,
    "rows": [
        {"english": e, "significance": s, "matched": m} for e, s, m in _SAMPLE_ROWS
    ],
    "bride": {
        "role": "BRIDE",
        "name": "anju",
        "am_id": "AM107958",
        "nakshatra": "Vishakam",
        "padam": 3,
        "rasi": "Thulam",
        "lagnam": "Kanni",
        "dasa": "05y 00m 09d",
        "lord": "Jupiter",
        "placements": {
            (0, 0): ["Gu", "Ra"], (1, 0): ["Shu"], (2, 0): ["Ra", "Bu"],
            (3, 0): ["Sha"], (3, 1): ["Ku", "Ma"], (3, 2): ["Cha"], (3, 3): ["La", "Ke"],
        },
        "amsa_placements": {
            (0, 0): ["Shu"], (0, 1): ["La"], (1, 0): ["Gu"], (1, 3): ["Ke", "Ma"],
            (2, 3): ["Cha", "Bu"], (3, 0): ["Ku", "Sha"], (3, 3): ["Ra"],
        },
        "bhava_placements": {
            (0, 0): ["La", "Cha"], (0, 3): ["Gu"], (1, 3): ["Ke"], (2, 0): ["Ku"],
            (3, 1): ["Bu", "Shu"], (3, 2): ["Sha"], (3, 3): ["Ra", "Ma"],
        },
    },
    "groom": {
        "role": "GROOM",
        "name": "arun as",
        "am_id": "AM107956",
        "nakshatra": "Ayilyam",
        "padam": 3,
        "rasi": "Kadakam",
        "lagnam": "Makaram",
        "dasa": "05y 10m 07d",
        "lord": "Mercury",
        "placements": {
            (0, 0): ["Ra"], (1, 0): ["Gu", "Ma"], (2, 0): ["La", "Ku"],
            (3, 1): ["Bu", "Sha"], (3, 2): ["Ra", "Gu"], (3, 3): ["Ke"], (1, 3): ["Cha"],
        },
        "amsa_placements": {
            (0, 0): ["Shu", "Ke"], (0, 2): ["La"], (1, 0): ["Ra"], (2, 0): ["Gu", "Cha"],
            (3, 0): ["Ku"], (3, 1): ["Bu"], (3, 3): ["Sha", "Ma"],
        },
        "bhava_placements": {
            (0, 0): ["La"], (1, 0): ["Ma", "Shu"], (1, 3): ["Gu", "Cha"], (2, 3): ["Ku"],
            (3, 0): ["Bu", "Sha"], (3, 2): ["Ra"], (3, 3): ["Ke"],
        },
    },
}


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "horoscope_matching_report_sample.pdf"
    pdf = build_horoscope_report_pdf(SAMPLE_REPORT)
    with open(out, "wb") as fh:
        fh.write(pdf)
    print(f"Wrote {out} ({len(pdf)} bytes)")


if __name__ == "__main__":
    main()
