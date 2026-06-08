"""
Horoscope string decoder for the Windows Horoscope Generator EXE bridge.

Single source of truth for decoding the EXE output strings
``pr_rasi`` / ``pr_amsa`` / ``pr_bhav`` into per-house planet placements.

The mappings used here are NOT guessed. They are defined once in
``astrology.charts`` and grounded in existing code:

* Character -> zodiac sign (A=1 .. L=12): ``astrology.porutham.chart_to_array``.
* Planet index -> planet: proven from ``astrology.porutham.calc_papatha``
  (reference points Lagna/Moon/Venus and the four malefics Sun/Mars/Saturn/Rahu)
  plus the fixed Rahu/Ketu opposition. See ``docs/horoscope_decoding.md``.

This module adds NO new mapping of its own; it only reshapes the decoded data
into the house-by-house form used by the debug API and verification tool.
"""
from __future__ import annotations

from typing import Any

from astrology.charts import PLANETS, decode_chart

# Planet abbreviation -> full planet name, derived from the single PLANETS table.
PLANET_ABBR_TO_NAME: dict[str, str] = {p['abbr']: p['name'] for p in PLANETS}
PLANET_KEY_TO_ABBR: dict[str, str] = {p['key']: p['abbr'] for p in PLANETS}


def _houses_by_abbr(encoded: str | None) -> dict[str, list[str]]:
    """Return ``{"1": ["Ju", "Sa"], ..., "12": []}`` for an 11-char EXE string."""
    decoded = decode_chart(encoded)
    return {
        house: [planet['abbr'] for planet in planets]
        for house, planets in decoded['houses'].items()
    }


def decode_rasi(raw_string: str | None) -> dict[str, list[str]]:
    """Decode ``pr_rasi`` into ``{house_number: [planet_abbr, ...]}`` (signs 1-12)."""
    return _houses_by_abbr(raw_string)


def decode_amsa(raw_string: str | None) -> dict[str, list[str]]:
    """Decode ``pr_amsa`` (Amsakom) into ``{house_number: [planet_abbr, ...]}``."""
    return _houses_by_abbr(raw_string)


def decode_bhava(raw_string: str | None) -> dict[str, list[str]]:
    """Decode ``pr_bhav`` (Bhavom) into ``{house_number: [planet_abbr, ...]}``."""
    return _houses_by_abbr(raw_string)


def decode_detailed(encoded: str | None) -> dict[str, Any]:
    """
    Verbose decode for the debug API and verification tool.

    Returns raw string, lagna sign, house->abbr map, and planet->sign detail.
    """
    decoded = decode_chart(encoded)
    return {
        'raw': encoded or '',
        'lagna_sign': decoded['lagna_sign'],
        'houses': {
            house: [planet['abbr'] for planet in planets]
            for house, planets in decoded['houses'].items()
        },
        'planets': {
            planet['name']: {
                'abbr': planet['abbr'],
                'sign': planet['sign'],
                'sign_name': planet['sign_name'],
            }
            for planet in decoded['planets']
        },
        'sign_names': decoded['sign_names'],
    }


def decode_bundle(
    raw_rasi: str | None,
    raw_amsa: str | None,
    raw_bhava: str | None,
    *,
    verbose: bool = False,
) -> dict[str, Any]:
    """
    Decode all three EXE chart strings at once for the debug API / report tool.

    Returns the exact shape requested by the verification task::

        {
          "raw_rasi": "AGEEHKGAEKJ",
          "raw_amsa": "EBAIIBCBAGA",
          "raw_bhava": "AGEFHKHAEKJ",
          "decoded_rasi":  {"1": ["La", "Sa"], ...},
          "decoded_amsa":  {...},
          "decoded_bhava": {...}
        }

    When ``verbose=True`` an extra ``detail`` key adds per-chart lagna sign and
    planet->sign breakdown (from :func:`decode_detailed`) for diagnostics.
    """
    bundle: dict[str, Any] = {
        'raw_rasi': raw_rasi or '',
        'raw_amsa': raw_amsa or '',
        'raw_bhava': raw_bhava or '',
        'decoded_rasi': decode_rasi(raw_rasi),
        'decoded_amsa': decode_amsa(raw_amsa),
        'decoded_bhava': decode_bhava(raw_bhava),
    }
    if verbose:
        bundle['detail'] = {
            'rasi': decode_detailed(raw_rasi),
            'amsa': decode_detailed(raw_amsa),
            'bhava': decode_detailed(raw_bhava),
        }
    return bundle
