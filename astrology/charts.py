"""Decode EXE horoscope chart strings (pr_rasi / pr_amsa / pr_bhav) for UI rendering."""
from __future__ import annotations

from typing import Any

from astrology.porutham import RASI_NAMES, STAR_NAMES, chart_to_array

# Planet order in the 11-char EXE strings (index -> planet).
PLANETS: list[dict[str, str]] = [
    {'key': 'la', 'abbr': 'La', 'name': 'Lagnam'},
    {'key': 'su', 'abbr': 'Su', 'name': 'Sun'},
    {'key': 'mo', 'abbr': 'Mo', 'name': 'Moon'},
    {'key': 'ma', 'abbr': 'Ma', 'name': 'Mars'},
    {'key': 'me', 'abbr': 'Me', 'name': 'Mercury'},
    {'key': 'ju', 'abbr': 'Ju', 'name': 'Jupiter'},
    {'key': 've', 'abbr': 'Ve', 'name': 'Venus'},
    {'key': 'sa', 'abbr': 'Sa', 'name': 'Saturn'},
    {'key': 'ra', 'abbr': 'Ra', 'name': 'Rahu'},
    {'key': 'ke', 'abbr': 'Ke', 'name': 'Ketu'},
    {'key': 'md', 'abbr': 'Md', 'name': 'Maandi'},
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

# EXE dasa balance display: 365-day year, month = 365/12 days.
DASA_YEAR_DAYS = 365
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
    if not signs or len(signs) < 11:
        return {
            'lagna_sign': None,
            'sign_names': _sign_names(),
            'houses': houses,
            'planets': [],
        }

    planets_out: list[dict[str, Any]] = []
    for idx, sign in enumerate(signs[:11]):
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
        'lagna_sign': signs[0] if signs else None,
        'sign_names': _sign_names(),
        'houses': houses,
        'planets': planets_out,
    }


def dasa_lord(star: int | None) -> str:
    """Vimshottari mahadasha lord at birth from nakshatra number (1-27)."""
    if not star or not (1 <= star <= 27):
        return ''
    return VIMSHOTTARI_LORDS[(star - 1) % 9]


def format_dasa_balance(days: int | None) -> dict[str, Any]:
    """
    Format pr_dasabalance (days) as y/m/d text matching the Windows EXE panel.

    Uses 365-day years and 365/12-day months (matches EXE e.g. 2459 -> 06y 08m 25d).
    """
    if days is None or days < 0:
        return {
            'years': 0,
            'months': 0,
            'days': 0,
            'balance_text': '',
        }

    years = int(days // DASA_YEAR_DAYS)
    rem_days = days - years * DASA_YEAR_DAYS
    months = int(rem_days // DASA_MONTH_DAYS)
    rem_day = int(rem_days - months * DASA_MONTH_DAYS)
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
            'name': STAR_NAMES[star_num] if star_num and 1 <= star_num <= 27 else '',
            'pada': pada,
        },
        'dasa': {
            'lord': dasa_lord(star_num),
            'balance_days': getattr(hp, 'pr_dasabalance', None) if hp else None,
            **balance,
        },
    }
