"""Decode EXE horoscope chart strings (pr_rasi / pr_amsa / pr_bhav) for UI rendering."""
from __future__ import annotations

from typing import Any

from astrology.porutham import RASI_NAMES, STAR_NAMES, chart_to_array

# Planet order in the 11-char EXE strings (index -> planet).
PLANETS: list[dict[str, str]] = [
    {'key': 'la', 'abbr': 'La', 'abbr_en': 'La', 'abbr_ml': 'ല', 'name': 'Lagnam'},
    {'key': 'su', 'abbr': 'Ra', 'abbr_en': 'Ra', 'abbr_ml': 'ര', 'name': 'Sun'},
    {'key': 'mo', 'abbr': 'Ch', 'abbr_en': 'Ch', 'abbr_ml': 'ച', 'name': 'Moon'},
    {'key': 'ma', 'abbr': 'Ku', 'abbr_en': 'Ku', 'abbr_ml': 'കു', 'name': 'Mars'},
    {'key': 'me', 'abbr': 'Bu', 'abbr_en': 'Bu', 'abbr_ml': 'ബു', 'name': 'Mercury'},
    {'key': 'ju', 'abbr': 'Gu', 'abbr_en': 'Gu', 'abbr_ml': 'ഗു', 'name': 'Jupiter'},
    {'key': 've', 'abbr': 'Sk', 'abbr_en': 'Sk', 'abbr_ml': 'ശു', 'name': 'Venus'},
    {'key': 'sa', 'abbr': 'Sn', 'abbr_en': 'Sn', 'abbr_ml': 'ശ', 'name': 'Saturn'},
    {'key': 'ra', 'abbr': 'Ra', 'abbr_en': 'Ra', 'abbr_ml': 'രാ', 'name': 'Rahu'},
    {'key': 'ke', 'abbr': 'Ke', 'abbr_en': 'Ke', 'abbr_ml': 'കേ', 'name': 'Ketu'},
    {'key': 'md', 'abbr': 'Md', 'abbr_en': 'Md', 'abbr_ml': 'മ', 'name': 'Maandi'},
]

VIMSHOTTARI_LORDS = [
    'Ketu',
    'Venus',
    'Sun',
    'Moon',
    'Mars',
    'Rahu',
    'Jupiter',
    'Saturn',
    'Mercury',
]

# EXE dasa balance display: 365.25-day year, month = 365.25/12 days.
DASA_YEAR_DAYS = 365.25
DASA_MONTH_DAYS = DASA_YEAR_DAYS / 12


def _empty_houses() -> dict[str, list[dict[str, str]]]:
    return {str(sign): [] for sign in range(1, 13)}


def _sign_names() -> dict[str, str]:
    return {str(sign): RASI_NAMES[sign] for sign in range(1, 13)}


def decode_chart(encoded: str | None) -> dict[str, Any]:
    """
    Convert an 11-char A-L string into per-sign planet placements.

    Each character position is a planet; the letter is the zodiac sign (A=1 .. L=12).
    """
    houses = _empty_houses()
    signs = chart_to_array(encoded)
    # chart_to_array returns a 1-indexed array: signs[0] is unused (0) and the
    # 11 planet signs live at signs[1..11].
    if not signs or len(signs) < 12:
        return {
            'lagna_sign': None,
            'sign_names': _sign_names(),
            'houses': houses,
            'planets': [],
        }

    planets_out: list[dict[str, Any]] = []
    for idx, sign in enumerate(signs[1:12]):
        planet = PLANETS[idx]
        entry = {
            'index': idx,
            **planet,
            'sign': sign,
            'sign_name': RASI_NAMES[sign] if 1 <= sign <= 12 else '',
        }
        planets_out.append(entry)
        if 1 <= sign <= 12:
            houses[str(sign)].append(planet)

    return {
        'lagna_sign': signs[1],
        'sign_names': _sign_names(),
        'houses': houses,
        'planets': planets_out,
    }


def dasa_lord(star: int | None) -> str:
    """Vimshottari mahadasha lord at birth from nakshatra number (1-27)."""
    if not star or not (1 <= star <= 27):
        return ''
    return VIMSHOTTARI_LORDS[(star - 1) % 9]


def star_name(star: int | None) -> str:
    """Nakshatra name from pr_star, independent of is_calculated."""
    if not star or not (1 <= star <= 27):
        return ''
    return STAR_NAMES[star]


def _rasi_name_from_chart(encoded: str | None, index: int) -> str:
    signs = chart_to_array(encoded)
    if len(signs) <= index:
        return ''
    sign = signs[index]
    return RASI_NAMES[sign] if 1 <= sign <= 12 else ''


def lagnam_name(encoded: str | None) -> str:
    """Lagnam name from pr_rasi. Position 1 is lagnam (1-indexed array)."""
    return _rasi_name_from_chart(encoded, 1)


def moon_rasi_name(encoded: str | None) -> str:
    """Moon rasi name from pr_rasi. Position 3 is Chandran (1-indexed array)."""
    return _rasi_name_from_chart(encoded, 3)


def format_dasa_balance(days: int | None) -> dict[str, Any]:
    """
    Format pr_dasabalance (days) as y/m/d text matching the Windows EXE panel.

    Uses 365.25-day years and 365.25/12-day months with inclusive day counting
    (matches EXE e.g. 4991 -> 13y 07m 30d, 3599 -> 09y 10m 08d).
    """
    if days is None or days <= 0:
        return {
            'years': 0,
            'months': 0,
            'days': 0,
            'balance_text': '',
        }

    years = int(days / DASA_YEAR_DAYS)
    rem_days = days - years * DASA_YEAR_DAYS
    months = int(rem_days / DASA_MONTH_DAYS)
    # EXE uses inclusive day counting: floor the fractional day, then +1.
    rem_day = int(rem_days - months * DASA_MONTH_DAYS) + 1
    if rem_day > 30:
        rem_day -= 30
        months += 1
    if months >= 12:
        months -= 12
        years += 1
    return {
        'years': years,
        'months': months,
        'days': rem_day,
        'balance_text': f'{years:02d}y {months:02d}m {rem_day:02d}d',
    }


def build_horoscope_charts(hp) -> dict[str, Any]:
    """Build decoded rasi/amsa/bhava charts plus star and dasa metadata for API output."""
    star_num = hp.pr_star if hp else None
    pada = hp.pr_pada if hp else None
    balance = format_dasa_balance(getattr(hp, 'pr_dasabalance', None))

    return {
        'rasi': decode_chart(getattr(hp, 'pr_rasi', None) if hp else None),
        'amsa': decode_chart(getattr(hp, 'pr_amsa', None) if hp else None),
        'bhava': decode_chart(getattr(hp, 'pr_bhav', None) if hp else None),
        'star': {
            'number': star_num,
            'name': star_name(star_num),
            'pada': pada,
        },
        'dasa': {
            'lord': dasa_lord(star_num),
            'balance_days': getattr(hp, 'pr_dasabalance', None) if hp else None,
            **balance,
        },
    }
