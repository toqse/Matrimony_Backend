import logging
from datetime import datetime
from datetime import timezone as dt_timezone

from django.utils import timezone

from .nakshatra_data import NAKSHATRA_DATA
from .utils import (
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
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    utc_dt = dt.astimezone(dt_timezone.utc)
    return swe.julday(
        utc_dt.year,
        utc_dt.month,
        utc_dt.day,
        utc_dt.hour + (utc_dt.minute / 60.0) + (utc_dt.second / 3600.0),
    )


def _planetary_positions(jd_ut):
    positions = {}
    for name, code in PLANET_CODES.items():
        result = swe.calc_ut(jd_ut, code)
        longitude = normalize_degree(result[0][0])
        positions[name] = {
            'longitude': longitude,
            'rasi': rasi_name_from_longitude(longitude),
            'short_name': PLANET_NAME_MAP[name],
        }

    moon_longitude = positions['moon']['longitude']
    rahu_longitude = normalize_degree(swe.calc_ut(jd_ut, swe.TRUE_NODE)[0][0])
    ketu_longitude = normalize_degree(rahu_longitude + 180.0)
    positions['rahu'] = {
        'longitude': rahu_longitude,
        'rasi': rasi_name_from_longitude(rahu_longitude),
        'short_name': PLANET_NAME_MAP['rahu'],
    }
    positions['ketu'] = {
        'longitude': ketu_longitude,
        'rasi': rasi_name_from_longitude(ketu_longitude),
        'short_name': PLANET_NAME_MAP['ketu'],
    }
    return positions, moon_longitude


def _lagna_from_houses(jd_ut, latitude, longitude):
    houses, _ = swe.houses_ex(jd_ut, latitude, longitude, b'P')
    ascendant_longitude = normalize_degree(houses[0])
    return rasi_name_from_longitude(ascendant_longitude), ascendant_longitude


def generate_horoscope_payload(date_of_birth, time_of_birth, place_of_birth):
    if swe is None:
        raise RuntimeError('pyswisseph is not installed or failed to import.')

    latitude, longitude = _geocode_place(place_of_birth)
    jd_ut = _julian_day_utc(date_of_birth, time_of_birth)

    positions, moon_longitude = _planetary_positions(jd_ut)
    lagna, lagna_longitude = _lagna_from_houses(jd_ut, latitude, longitude)

    nakshatra_index = nakshatra_index_from_longitude(moon_longitude)
    nakshatra = NAKSHATRA_DATA[nakshatra_index]
    nakshatra_pada = nakshatra_pada_from_longitude(moon_longitude)

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
        },
        'birth_input_hash': build_birth_input_hash(
            date_of_birth=date_of_birth,
            time_of_birth=time_of_birth,
            place_of_birth=place_of_birth,
        ),
    }
    logger.info(
        'Horoscope generated for place=%s rasi=%s nakshatra=%s',
        place_of_birth,
        payload['rasi'],
        payload['nakshatra'],
    )
    return payload
