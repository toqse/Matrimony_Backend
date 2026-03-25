import logging
from contextlib import contextmanager
from datetime import datetime
from datetime import timezone as dt_timezone

from django.conf import settings
from django.utils import timezone

from .nakshatra_data import NAKSHATRA_DATA
from .utils import (
    PLANET_FULL_NAMES,
    PLANET_NAME_MAP,
    build_birth_input_hash,
    nakshatra_index_from_longitude,
    nakshatra_pada_from_longitude,
    normalize_degree,
    rasi_name_from_longitude,
)

logger = logging.getLogger(__name__)

try:
    from geopy.geocoders import Nominatim
except Exception:  # pragma: no cover - runtime dependency
    Nominatim = None

try:
    import swisseph as swe
except Exception:  # pragma: no cover - runtime dependency
    swe = None


PLANET_CODES = {
    'sun': 0,
    'moon': 1,
    'mars': 4,
    'mercury': 2,
    'jupiter': 5,
    'venus': 3,
    'saturn': 6,
}


def _use_sidereal() -> bool:
    return bool(getattr(settings, 'ASTROLOGY_SIDEREAL', True))

def _swe_flag(name: str, default: int = 0) -> int:
    if swe is None:
        return default
    return int(getattr(swe, name, getattr(swe, f'SE_{name}', default)))


def _calc_flags(use_sidereal: bool) -> int:
    """
    Swiss Ephemeris calculation flags.
    Prokerala parity requires explicit sidereal longitudes when using Lahiri.
    """
    # Prefer SWIEPH, include speed (harmless) and sidereal when requested.
    base = _swe_flag('FLG_SWIEPH', 2) | _swe_flag('FLG_SPEED', 256)
    if use_sidereal:
        base |= _swe_flag('FLG_SIDEREAL', 64)
    return int(base)


def _lahiri_mode_constant():
    return getattr(swe, 'SIDM_LAHIRI', getattr(swe, 'SE_SIDM_LAHIRI', 1))


def _tropical_mode_constant():
    for name in ('SIDM_NONE', 'SE_SIDM_NONE'):
        if hasattr(swe, name):
            return getattr(swe, name)
    return -1


@contextmanager
def _swiss_ephemeris_sidereal_context(use_sidereal: bool):
    """Set Swiss Ephemeris sidereal (Lahiri) or tropical for the duration of the block."""
    if swe is None:
        yield
        return
    prev = None
    if hasattr(swe, 'get_sid_mode'):
        try:
            prev = swe.get_sid_mode()
        except Exception:
            prev = None
    try:
        if use_sidereal:
            swe.set_sid_mode(_lahiri_mode_constant())
        else:
            swe.set_sid_mode(_tropical_mode_constant())
        yield
    finally:
        if prev is not None:
            try:
                if isinstance(prev, (tuple, list)) and len(prev) >= 3:
                    swe.set_sid_mode(int(prev[0]), float(prev[1]), float(prev[2]))
                elif isinstance(prev, (tuple, list)) and len(prev) >= 1:
                    swe.set_sid_mode(int(prev[0]))
                else:
                    swe.set_sid_mode(int(prev))
            except Exception:
                try:
                    swe.set_sid_mode(_tropical_mode_constant())
                except Exception:
                    pass


def _geocode_place(place_of_birth: str):
    if Nominatim is None:
        raise RuntimeError('geopy is not installed or failed to import.')
    geolocator = Nominatim(user_agent='matrimony_astrology')
    location = geolocator.geocode(place_of_birth, timeout=10)
    if not location:
        raise ValueError('Unable to resolve place_of_birth.')
    return float(location.latitude), float(location.longitude)


def _julian_day_utc(date_of_birth, time_of_birth):
    dt = datetime.combine(date_of_birth, time_of_birth)
    if timezone.is_naive(dt):
        # Interpret naive birth times in the project's configured timezone (Asia/Kolkata by default).
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    utc_dt = dt.astimezone(dt_timezone.utc)
    return swe.julday(
        utc_dt.year,
        utc_dt.month,
        utc_dt.day,
        utc_dt.hour + (utc_dt.minute / 60.0) + (utc_dt.second / 3600.0),
    )


def _planetary_positions(jd_ut, use_sidereal: bool):
    positions = {}
    with _swiss_ephemeris_sidereal_context(use_sidereal):
        flags = _calc_flags(use_sidereal)
        for name, code in PLANET_CODES.items():
            # calc_ut(jd, planet, flags) returns (xx, retflags) in pyswisseph
            result = swe.calc_ut(jd_ut, code, flags)
            longitude = normalize_degree(result[0][0])
            positions[name] = {
                'longitude': longitude,
                'rasi': rasi_name_from_longitude(longitude),
                'short_name': PLANET_NAME_MAP[name],
                'full_name': PLANET_FULL_NAMES[name],
            }

        moon_longitude = positions['moon']['longitude']
        rahu_longitude = normalize_degree(swe.calc_ut(jd_ut, swe.TRUE_NODE, flags)[0][0])
        ketu_longitude = normalize_degree(rahu_longitude + 180.0)
        positions['rahu'] = {
            'longitude': rahu_longitude,
            'rasi': rasi_name_from_longitude(rahu_longitude),
            'short_name': PLANET_NAME_MAP['rahu'],
            'full_name': PLANET_FULL_NAMES['rahu'],
        }
        positions['ketu'] = {
            'longitude': ketu_longitude,
            'rasi': rasi_name_from_longitude(ketu_longitude),
            'short_name': PLANET_NAME_MAP['ketu'],
            'full_name': PLANET_FULL_NAMES['ketu'],
        }
    return positions, moon_longitude


def _lagna_longitude(jd_ut, latitude, longitude, use_sidereal: bool):
    with _swiss_ephemeris_sidereal_context(use_sidereal):
        # Houses are computed in tropical; for sidereal lagna we subtract ayanamsa.
        # Swiss Ephemeris does not guarantee sidereal houses in all bindings.
        _, ascmc = swe.houses_ex(jd_ut, latitude, longitude, b'P')
        asc_tropical = normalize_degree(ascmc[0])
        if not use_sidereal:
            return asc_tropical
        ayanamsa = float(swe.get_ayanamsa_ut(jd_ut))
        return normalize_degree(asc_tropical - ayanamsa)


def generate_horoscope_payload(date_of_birth, time_of_birth, place_of_birth):
    if swe is None:
        raise RuntimeError('pyswisseph is not installed or failed to import.')

    use_sidereal = _use_sidereal()
    latitude, longitude = _geocode_place(place_of_birth)
    jd_ut = _julian_day_utc(date_of_birth, time_of_birth)

    positions, moon_longitude = _planetary_positions(jd_ut, use_sidereal)
    lagna_longitude = _lagna_longitude(jd_ut, latitude, longitude, use_sidereal)
    lagna = rasi_name_from_longitude(lagna_longitude)

    nakshatra_index = nakshatra_index_from_longitude(moon_longitude)
    nakshatra = NAKSHATRA_DATA[nakshatra_index]
    nakshatra_pada = nakshatra_pada_from_longitude(moon_longitude)

    chart_basis = (
        {'zodiac': 'sidereal', 'ayanamsa': 'lahiri'}
        if use_sidereal
        else {'zodiac': 'tropical', 'ayanamsa': None}
    )

    payload = {
        'date_of_birth': date_of_birth,
        'time_of_birth': time_of_birth,
        'place_of_birth': place_of_birth.strip(),
        'latitude': latitude,
        'longitude': longitude,
        'lagna': lagna,
        'rasi': rasi_name_from_longitude(moon_longitude),
        'nakshatra': nakshatra['name'],
        'nakshatra_pada': nakshatra_pada,
        'gana': nakshatra['gana'],
        'yoni': nakshatra['yoni'],
        'nadi': nakshatra['nadi'],
        'rajju': nakshatra['rajju'],
        'grahanila': {
            'lagna_longitude': lagna_longitude,
            'planets': positions,
            'chart_basis': chart_basis,
        },
        'birth_input_hash': build_birth_input_hash(
            date_of_birth=date_of_birth,
            time_of_birth=time_of_birth,
            place_of_birth=place_of_birth,
        ),
    }
    if bool(getattr(settings, 'ASTROLOGY_DEBUG_TRACE', False)):
        try:
            payload['grahanila']['debug'] = {
                'jd_ut': float(jd_ut),
                'use_sidereal': bool(use_sidereal),
                'calc_flags': int(_calc_flags(use_sidereal)),
                'ayanamsa_ut': float(swe.get_ayanamsa_ut(jd_ut)) if use_sidereal else None,
            }
        except Exception:
            payload['grahanila']['debug'] = {'jd_ut': float(jd_ut), 'use_sidereal': bool(use_sidereal)}
    logger.info(
        'Horoscope generated for place=%s rasi=%s nakshatra=%s sidereal=%s',
        place_of_birth,
        payload['rasi'],
        payload['nakshatra'],
        use_sidereal,
    )
    return payload
