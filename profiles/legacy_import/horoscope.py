"""Star-name → number lookup and HoroscopeProfile persistence.

The canonical 1-27 nakshatra list lives in `astrology.porutham.STAR_NAMES`.
Legacy data uses Malayalam Roman spellings (Anizham, Chithira, Avittom, etc.)
that don't all match the canonical names. We extend the lookup with the
spellings actually present in the export so we don't silently drop stars.
"""
from __future__ import annotations

from typing import Optional

from astrology.models import HoroscopeProfile
from astrology.porutham import STAR_NAMES

from .normalize import clean, parse_int

# Legacy Roman/Malayalam spellings → canonical nakshatra index (1-27).
LEGACY_STAR_ALIASES = {
    "aswathy": 1,
    "aswathi": 1,
    "karthika": 3,
    "rohiny": 4,
    "mrigasira": 5,
    "makayiram": 5,
    "makayeeram": 5,
    "aayilliam": 9,
    "makom": 10,
    "chithira": 14,
    "chithra": 14,
    "chothy": 15,
    "chothi": 15,
    "visakom": 16,
    "thrikketta": 18,
    "pooradom": 20,
    "uthradom": 21,
    "avittom": 23,
    "chathayom": 24,
    "uthrattathi": 26,
    "uthuruttathi": 26,
    "uthrittathi": 26,
}


def star_lookup() -> dict[str, int]:
    """Build the case-insensitive star-name → number map (canonical + aliases)."""
    mapping = {name.lower(): index for index, name in enumerate(STAR_NAMES) if name}
    mapping.update(LEGACY_STAR_ALIASES)
    return mapping


def resolve_star(raw: object, lookup: dict[str, int]) -> tuple[Optional[int], str]:
    """Return (star_number, warning_label).

    `warning_label` is the original spelling when we couldn't map it, so the
    caller can emit a row-level warning into the import report.
    """
    text = clean(raw)
    if not text:
        return None, ""
    number = lookup.get(text.lower())
    if number:
        return number, ""
    return None, text


def resolve_padam(raw: object) -> Optional[int]:
    """Padam is 1-4; legacy uses 0 to mean unknown."""
    value = parse_int(raw)
    if 1 <= value <= 4:
        return value
    return None


def upsert_horoscope_profile(user, payload: dict) -> Optional[HoroscopeProfile]:
    """Create or update HoroscopeProfile for `user` from a built payload.

    Returns the row when any chart/star data was present, else None.
    `is_calculated` is True only when both rasi chart and star are present;
    that's what the porutham service treats as 'EXE finished'.
    """
    has_chart = bool(
        payload.get("pr_rasi")
        or payload.get("pr_amsa")
        or payload.get("pr_bhav")
        or payload.get("pr_star")
    )
    if not has_chart:
        return None
    obj, _ = HoroscopeProfile.objects.update_or_create(
        user=user,
        defaults={
            "pr_name": user.name,
            "pr_dob": user.dob,
            "pr_rasi": payload.get("pr_rasi") or "",
            "pr_amsa": payload.get("pr_amsa") or "",
            "pr_bhav": payload.get("pr_bhav") or "",
            "pr_dasabalance": payload.get("pr_dasabalance") or None,
            "pr_star": payload.get("pr_star"),
            "pr_pada": payload.get("pr_pada"),
            "is_calculated": bool(payload.get("pr_rasi") and payload.get("pr_star")),
        },
    )
    return obj
