from __future__ import annotations

import logging
import os
import unicodedata
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

logger = logging.getLogger(__name__)

from .chart_malayalam_data import (
    GENDER_MLY,
    LAGNA_MLY,
    NAKSHATRA_MALAYALAM,
    PLANET_MLY,
    RASI_LABEL_MLY,
    RASI_TO_GRID,
    TITLE_MLY,
)
from .utils import rasi_name_from_longitude

# 12 perimeter cells, clockwise from top-left (South Indian fixed-rasi chart)
PERIMETER_CELLS = [
    (0, 0),
    (1, 0),
    (2, 0),
    (3, 0),
    (3, 1),
    (3, 2),
    (3, 3),
    (2, 3),
    (1, 3),
    (0, 3),
    (0, 2),
    (0, 1),
]

_GRID_POS_TO_RASI = {v: k for k, v in RASI_TO_GRID.items()}

# BCP 47 — enables HarfBuzz shaping via Pillow+Raqm (vowel signs, conjuncts)
_MALAYALAM_LANG = 'ml'


def _normalize_ml(text: str) -> str:
    """NFC so precomposed Malayalam clusters match the font’s cmap."""
    if not text:
        return text
    return unicodedata.normalize('NFC', text)


def _ct_layout_kwargs() -> dict:
    """
    Complex text layout for Malayalam. Requires Pillow linked with libraqm
    (HarfBuzz + FriBidi). Without Raqm, glyphs show dotted circles / wrong matras.
    """
    try:
        if features.check('raqm'):
            return {'language': _MALAYALAM_LANG}
    except Exception:
        pass
    return {}


def _warn_if_no_raqm() -> None:
    try:
        if not features.check('raqm'):
            logger.warning(
                'Pillow has no Raqm (libraqm): Malayalam will not shape correctly. '
                'Docker: install libraqm0 libharfbuzz0b libfribidi0; '
                'Windows/macOS: use current Pillow wheels from PyPI (they bundle Raqm).'
            )
    except Exception:
        pass


def _font_path() -> str | None:
    base = Path(__file__).resolve().parent.parent / 'fonts' / 'NotoSansMalayalam-Regular.ttf'
    if base.exists():
        return str(base)
    env = os.environ.get('MALAYALAM_FONT_PATH')
    if env and Path(env).exists():
        return env
    return None


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _font_path()
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _cell_bbox(margin: float, cw: float, ch: float, gx: int, gy: int) -> tuple[float, float, float, float]:
    x0 = margin + gx * cw
    y0 = margin + gy * ch
    return (x0, y0, x0 + cw, y0 + ch)


def _center_bbox(margin: float, cw: float, ch: float) -> tuple[float, float, float, float]:
    return (margin + cw, margin + ch, margin + 3 * cw, margin + 3 * ch)


def _build_cell_symbols(grahanila: dict | None) -> dict[tuple[int, int], list[str]]:
    """Map grid cell -> ordered Malayalam symbols (ലഗ്നം first if present, then grahas)."""
    cells: dict[tuple[int, int], list[str]] = {}
    data = grahanila or {}
    lagna_lon = data.get('lagna_longitude')
    planets = data.get('planets') or {}

    if lagna_lon is not None:
        lr = rasi_name_from_longitude(float(lagna_lon))
        pos = RASI_TO_GRID.get(lr)
        if pos:
            cells.setdefault(pos, []).append(LAGNA_MLY)

    # Stable planet order for consistent layout
    planet_order = (
        'sun', 'moon', 'mars', 'mercury', 'jupiter', 'venus', 'saturn', 'rahu', 'ketu',
    )
    for key in planet_order:
        info = planets.get(key)
        if not info:
            continue
        lon = info.get('longitude')
        if lon is None:
            continue
        rasi = rasi_name_from_longitude(float(lon))
        pos = RASI_TO_GRID.get(rasi)
        if not pos:
            continue
        sym = PLANET_MLY.get(key)
        if sym:
            cells.setdefault(pos, []).append(sym)

    return cells


def _cell_text_lines(symbols: list[str]) -> list[str]:
    if not symbols:
        return []
    lagna_parts = [s for s in symbols if s == LAGNA_MLY]
    grahas = [s for s in symbols if s != LAGNA_MLY]
    lines: list[str] = []
    if lagna_parts:
        lines.append(LAGNA_MLY)
    if grahas:
        lines.append(' '.join(grahas))
    return lines


def _draw_south_indian_malayalam(
    grahanila: dict,
    *,
    nakshatra_en: str | None = None,
    gender_code: str | None = None,
) -> bytes:
    size = 1200
    margin = 36
    inner = size - 2 * margin
    cw = inner / 4.0
    ch = inner / 4.0

    img = Image.new('RGB', (size, size), color='#fffef8')
    draw = ImageDraw.Draw(img)
    outline = '#2c1810'
    width = 3

    font_rasi = _load_font(17)
    font_body = _load_font(26)
    font_center = _load_font(30)
    _warn_if_no_raqm()
    layout_kw = _ct_layout_kwargs()

    for gx, gy in PERIMETER_CELLS:
        box = _cell_bbox(margin, cw, ch, gx, gy)
        draw.rectangle(box, outline=outline, width=width)

    cbox = _center_bbox(margin, cw, ch)
    draw.rectangle(cbox, outline=outline, width=width)

    # Rasi name at top of each outer cell
    for gx, gy in PERIMETER_CELLS:
        rasi = _GRID_POS_TO_RASI.get((gx, gy))
        if not rasi:
            continue
        label = _normalize_ml(RASI_LABEL_MLY.get(rasi, rasi))
        box = _cell_bbox(margin, cw, ch, gx, gy)
        draw.text(
            (box[0] + 8, box[1] + 6),
            label,
            font=font_rasi,
            fill='#4a3728',
            **layout_kw,
        )

    cell_symbols = _build_cell_symbols(grahanila)
    # Space reserved at top for rāśi name; graha block centered in the rest (like paper charts).
    rasi_label_reserve = 36
    cell_pad = 6
    line_gap_body = max(6, int(font_body.size * 0.32))

    for gx, gy in PERIMETER_CELLS:
        syms = cell_symbols.get((gx, gy), [])
        lines = _cell_text_lines(syms)
        if not lines:
            continue
        box = _cell_bbox(margin, cw, ch, gx, gy)
        inner_left = box[0] + cell_pad
        inner_right = box[2] - cell_pad
        inner_top = box[1] + rasi_label_reserve
        inner_bottom = box[3] - cell_pad
        cx = (inner_left + inner_right) / 2.0
        cy = (inner_top + inner_bottom) / 2.0
        body_text = '\n'.join(_normalize_ml(line) for line in lines)
        draw.multiline_text(
            (cx, cy),
            body_text,
            font=font_body,
            fill='#000000',
            anchor='mm',
            align='center',
            spacing=line_gap_body,
            **layout_kw,
        )

    # Center panel: ഗ്രഹനില + gender + nakshatra (Malayalam)
    center_lines = [TITLE_MLY]
    g = (gender_code or '').strip().upper()[:1] or ''
    gtxt = GENDER_MLY.get(g, '')
    if gtxt:
        center_lines.append(gtxt)
    if nakshatra_en:
        nk = NAKSHATRA_MALAYALAM.get(nakshatra_en.strip(), nakshatra_en)
        if nk:
            center_lines.append(nk)

    ctext = '\n'.join(_normalize_ml(line) for line in center_lines if line)
    cx = (cbox[0] + cbox[2]) / 2.0
    cy = (cbox[1] + cbox[3]) / 2.0
    draw.multiline_text(
        (cx, cy),
        ctext,
        font=font_center,
        fill='#1a1008',
        anchor='mm',
        align='center',
        spacing=12,
        **layout_kw,
    )

    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _generate_north_placeholder(grahanila: dict) -> bytes:
    """Simple fallback when style=north (not Kerala square chart)."""
    from .utils import rasi_name_from_longitude as rnf

    image = Image.new('RGB', (900, 900), color='white')
    draw = ImageDraw.Draw(image)
    step = 225
    for i in range(5):
        draw.line((0, i * step, 900, i * step), fill='black', width=2)
        draw.line((i * step, 0, i * step, 900), fill='black', width=2)
    planets = (grahanila or {}).get('planets', {})
    y = 20
    draw.text((20, y), 'North style (summary)', fill='black')
    y += 40
    for name, info in planets.items():
        lon = info.get('longitude')
        if lon is None:
            continue
        r = rnf(float(lon))
        draw.text((20, y), f'{name}: {r}', fill='black')
        y += 28
    buf = BytesIO()
    image.save(buf, format='PNG')
    return buf.getvalue()


def generate_chart_image(
    grahanila: dict,
    style: str = 'south',
    *,
    nakshatra_en: str | None = None,
    gender_code: str | None = None,
) -> bytes:
    if style not in ('south', 'north'):
        style = 'south'
    if style == 'north':
        return _generate_north_placeholder(grahanila)
    return _draw_south_indian_malayalam(
        grahanila,
        nakshatra_en=nakshatra_en,
        gender_code=gender_code,
    )
