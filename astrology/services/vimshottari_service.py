"""Vimshottari mahadasha balance (approximate) for UI center panel."""
from __future__ import annotations

from datetime import datetime, timezone

from django.utils import timezone as dj_tz

from .utils import normalize_degree

LORD_KEYS = (
    'KETU',
    'VENUS',
    'SUN',
    'MOON',
    'MARS',
    'RAHU',
    'JUPITER',
    'SATURN',
    'MERCURY',
)
LORD_YEARS = (7, 20, 6, 10, 7, 18, 16, 19, 17)
LORD_DISPLAY = {
    'KETU': 'KETU',
    'VENUS': 'SUKRAN',
    'SUN': 'RAVI',
    'MOON': 'CHANDRA',
    'MARS': 'KUJA',
    'RAHU': 'RAHU',
    'JUPITER': 'GURU',
    'SATURN': 'SANI',
    'MERCURY': 'BUDHA',
}

YEAR_DAYS = 365.24219


def _birth_utc(horoscope) -> datetime:
    dt = datetime.combine(horoscope.date_of_birth, horoscope.time_of_birth)
    if dj_tz.is_naive(dt):
        dt = dj_tz.make_aware(dt, dj_tz.get_current_timezone())
    return dt.astimezone(timezone.utc)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dj_tz.make_aware(dt, dj_tz.get_current_timezone())
    return dt.astimezone(timezone.utc)


def vimshottari_mahadasha_state(horoscope, ref_utc: datetime | None = None) -> dict | None:
    """
    Current Vimshottari mahadasha lord and approximate time left in the period.
    Uses moon longitude at birth from stored grahanila.
    """
    grahanila = horoscope.grahanila or {}
    moon = (grahanila.get('planets') or {}).get('moon') or {}
    lon = moon.get('longitude')
    if lon is None:
        return None

    ref_utc = _to_utc(ref_utc or datetime.now(timezone.utc))
    birth_utc = _birth_utc(horoscope)
    moon_deg = normalize_degree(float(lon))

    nak_size = 360.0 / 27.0
    nak_index = int(moon_deg // nak_size)
    elapsed_deg = moon_deg - nak_index * nak_size
    elapsed_fraction = max(0.0, min(1.0, elapsed_deg / nak_size))

    lord_idx = nak_index % 9
    balance_years = (1.0 - elapsed_fraction) * LORD_YEARS[lord_idx]

    if ref_utc <= birth_utc:
        rem_sec = balance_years * YEAR_DAYS * 86400.0
        lord_key = LORD_KEYS[lord_idx]
        return _state_dict(lord_key, rem_sec)

    elapsed_sec = (ref_utc - birth_utc).total_seconds()
    li = lord_idx
    period_sec = balance_years * YEAR_DAYS * 86400.0

    while elapsed_sec >= period_sec and period_sec > 0:
        elapsed_sec -= period_sec
        li = (li + 1) % 9
        period_sec = LORD_YEARS[li] * YEAR_DAYS * 86400.0

    remaining_sec = max(0.0, period_sec - elapsed_sec)
    return _state_dict(LORD_KEYS[li], remaining_sec)


def _state_dict(lord_key: str, remaining_sec: float) -> dict:
    y, m, d = _ymd_from_seconds(remaining_sec)
    return {
        'lord_key': lord_key,
        'lord': LORD_DISPLAY.get(lord_key, lord_key),
        'remaining': {'years': y, 'months': m, 'days': d},
        'remaining_label': f'{y:02d}y {m:02d}m {d:02d}d',
        'remaining_seconds': int(remaining_sec),
    }


def _ymd_from_seconds(sec: float) -> tuple[int, int, int]:
    if sec <= 0:
        return 0, 0, 0
    days_total = int(sec // 86400)
    years = int(days_total // YEAR_DAYS)
    rem_days = int(days_total - years * YEAR_DAYS)
    months = int(rem_days // 30)
    days = int(rem_days - months * 30)
    return years, months, days


def seconds_until_mahadasha_end(horoscope, ref_utc: datetime | None = None) -> float | None:
    ref = _to_utc(ref_utc or datetime.now(timezone.utc))
    st = vimshottari_mahadasha_state(horoscope, ref)
    if not st:
        return None
    return float(st['remaining_seconds'])
