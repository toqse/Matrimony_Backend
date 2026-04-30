import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from .nakshatra_data import NAKSHATRA_DATA
from .utils import (
    PLANET_FULL_NAMES,
    PLANET_NAME_MAP,
    RASI_NAMES,
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


def _birth_timezone():
    tz_name = str(getattr(settings, 'ASTROLOGY_BIRTH_TIMEZONE', 'Asia/Kolkata') or 'Asia/Kolkata')
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo('Asia/Kolkata')

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


def _rise_trans_flags() -> int:
    """Tropical ephemeris flags for rise/set only (do not use FLG_SIDEREAL here)."""
    return int(_swe_flag('FLG_SWIEPH', 2) | _swe_flag('FLG_SPEED', 256))


def _normalize_place_key(place: str) -> str:
    s = (place or '').strip().lower()
    for ch in ',.;':
        s = s.replace(ch, ' ')
    return ' '.join(s.split())


def _fallback_lat_lon(place: str) -> tuple[float, float] | None:
    """Stable coordinates for common Kerala place strings (reduces Nominatim variance vs desktop apps)."""
    n = _normalize_place_key(place)
    overrides = getattr(settings, 'ASTROLOGY_PLACE_COORDINATES', None) or {}
    if isinstance(overrides, dict):
        for key, pair in overrides.items():
            nk = _normalize_place_key(str(key))
            if not nk:
                continue
            if nk == n or nk in n or n in nk:
                try:
                    lat, lon = pair[0], pair[1]
                    return float(lat), float(lon)
                except (IndexError, TypeError, ValueError):
                    continue
    # Built-ins: substring match on normalized place_of_birth
    if 'ernakulam' in n or 'kochi' in n or 'cochin' in n:
        return 9.9816, 76.267304
    if 'alappuzha' in n or 'alleppey' in n:
        return 9.4981, 76.338848
    return None


def _resolve_lat_lon(place_of_birth: str) -> tuple[float, float]:
    fb = _fallback_lat_lon(place_of_birth)
    if fb is not None:
        return fb
    return _geocode_place(place_of_birth)


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
        # Birth time is local civil time in astrology timezone (IST default).
        dt = timezone.make_aware(dt, _birth_timezone())
    utc_dt = dt.astimezone(dt_timezone.utc)
    return swe.julday(
        utc_dt.year,
        utc_dt.month,
        utc_dt.day,
        utc_dt.hour + (utc_dt.minute / 60.0) + (utc_dt.second / 3600.0),
    )


def _julian_day_from_aware(dt_value: datetime) -> float:
    utc_dt = dt_value.astimezone(dt_timezone.utc)
    return swe.julday(
        utc_dt.year,
        utc_dt.month,
        utc_dt.day,
        utc_dt.hour + (utc_dt.minute / 60.0) + (utc_dt.second / 3600.0),
    )


def _sun_event_jd(local_date, latitude: float, longitude: float, event: str) -> float | None:
    """
    Return UTC Julian Day for sunrise/sunset at location on a local civil date.
    Uses Swiss Ephemeris rise_trans with compatibility fallbacks across bindings.
    """
    tz = _birth_timezone()
    local_noon = timezone.make_aware(datetime.combine(local_date, datetime.min.time().replace(hour=12)), tz)
    jd_ref = _julian_day_from_aware(local_noon)
    rsmi = _swe_flag('CALC_RISE' if event == 'rise' else 'CALC_SET')
    geopos = (float(longitude), float(latitude), 0.0)
    flags = _rise_trans_flags()

    attempts = (
        lambda: swe.rise_trans(jd_ref, swe.SUN, rsmi, geopos, 0.0, 0.0, flags),
        lambda: swe.rise_trans(jd_ref, swe.SUN, rsmi, geopos),
        lambda: swe.rise_trans(jd_ref, swe.SUN, float(longitude), float(latitude), rsmi),
    )
    for call in attempts:
        try:
            result = call()
        except Exception:
            continue
        if not result:
            continue
        times = result[1] if isinstance(result, (tuple, list)) and len(result) > 1 else None
        if isinstance(times, (tuple, list)) and times:
            return float(times[0])
    return None


def _vedic_weekday(d) -> int:
    """Sunday=0 … Saturday=6 (Python weekday is Mon=0; convert for traditional tables)."""
    return int((d.weekday() + 1) % 7)


def _gulika_segment_index(vedic_weekday: int, is_daytime: bool) -> int:
    # Segment index is zero-based over the 8 equal divisions.
    day_segments = (6, 5, 4, 3, 2, 1, 0)   # Sun..Sat -> Gulika daytime parts (7th .. 1st)
    night_segments = (5, 4, 3, 2, 1, 0, 6)  # Gulika nighttime parts
    return (day_segments if is_daytime else night_segments)[vedic_weekday % 7]


def _yamaghanta_segment_index(vedic_weekday: int, is_daytime: bool) -> int:
    """
    Yamaghantaka (Yamaganda kāla midpoint): Jupiter's ⅛ daytime / night arcs.
    Daytime indices from common Panchang tables (Sunday = 5th division → segment 4 …).
    """
    day_segments = (4, 3, 2, 1, 0, 6, 5)    # Sun..Sat Yamaganda day
    night_segments = (3, 2, 1, 0, 7, 5, 4)  # Night arc (paired to day block)
    return (day_segments if is_daytime else night_segments)[vedic_weekday % 7]


def _birth_kala_arc(
    date_of_birth,
    time_of_birth,
    latitude: float,
    longitude: float,
) -> tuple[float, float, int, bool] | None:
    """
    Return (segment_start_jd, segment_end_jd, vedic_weekday_for_arc, is_daytime)
    covering the sunrise–sunset or sunset–sunrise arc applicable to kāla subdivision.
    """
    tz = _birth_timezone()
    birth_local = timezone.make_aware(datetime.combine(date_of_birth, time_of_birth), tz)
    birth_jd = _julian_day_from_aware(birth_local)

    sunrise_today = _sun_event_jd(date_of_birth, latitude, longitude, event='rise')
    sunset_today = _sun_event_jd(date_of_birth, latitude, longitude, event='set')
    if sunrise_today is None or sunset_today is None:
        return None

    if sunrise_today <= birth_jd < sunset_today:
        return (
            sunrise_today,
            sunset_today,
            _vedic_weekday(date_of_birth),
            True,
        )

    if birth_jd < sunrise_today:
        prev_date = date_of_birth - timedelta(days=1)
        prev_sunset = _sun_event_jd(prev_date, latitude, longitude, event='set')
        if prev_sunset is None:
            return None
        segment_start = prev_sunset
        segment_end = sunrise_today
        vwd = _vedic_weekday(prev_date)
        return segment_start, segment_end, vwd, False

    next_date = date_of_birth + timedelta(days=1)
    next_sunrise = _sun_event_jd(next_date, latitude, longitude, event='rise')
    if next_sunrise is None:
        return None
    segment_start = sunset_today
    segment_end = next_sunrise
    vwd = _vedic_weekday(date_of_birth)
    return segment_start, segment_end, vwd, False


def _kala_arc_midpoint_longitude(
    date_of_birth,
    time_of_birth,
    latitude: float,
    longitude: float,
    use_sidereal: bool,
    segment_resolver,
) -> float | None:
    arc = _birth_kala_arc(date_of_birth, time_of_birth, latitude, longitude)
    if arc is None:
        return None
    segment_start, segment_end, vwd, is_daytime = arc
    duration = segment_end - segment_start
    if duration <= 0:
        return None
    seg = segment_resolver(vwd, is_daytime)
    segment_mid_jd = segment_start + ((seg + 0.5) * (duration / 8.0))
    return _lagna_longitude(segment_mid_jd, latitude, longitude, use_sidereal)


def _gulika_longitude(
    date_of_birth,
    time_of_birth,
    latitude: float,
    longitude: float,
    use_sidereal: bool,
) -> float | None:
    """Gulika (Mandi): midpoint of Saturn's ⅛ day / night kāla."""

    def _resolver(vwd: int, is_daytime: bool) -> int:
        return _gulika_segment_index(vwd, is_daytime)

    return _kala_arc_midpoint_longitude(
        date_of_birth,
        time_of_birth,
        latitude,
        longitude,
        use_sidereal,
        _resolver,
    )


def _yamaghanta_longitude(
    date_of_birth,
    time_of_birth,
    latitude: float,
    longitude: float,
    use_sidereal: bool,
) -> float | None:
    """Yamaghantaka: midpoint of Jupiter's ⅛ day / night kāla (yamaganda)."""

    def _resolver(vwd: int, is_daytime: bool) -> int:
        return _yamaghanta_segment_index(vwd, is_daytime)

    return _kala_arc_midpoint_longitude(
        date_of_birth,
        time_of_birth,
        latitude,
        longitude,
        use_sidereal,
        _resolver,
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
    latitude, longitude = _resolve_lat_lon(place_of_birth)
    jd_ut = _julian_day_utc(date_of_birth, time_of_birth)

    positions, moon_longitude = _planetary_positions(jd_ut, use_sidereal)
    gulika_longitude = _gulika_longitude(
        date_of_birth,
        time_of_birth,
        latitude,
        longitude,
        use_sidereal,
    )
    if gulika_longitude is not None:
        positions['gulika'] = {
            'longitude': gulika_longitude,
            'rasi': rasi_name_from_longitude(gulika_longitude),
            'short_name': PLANET_NAME_MAP['gulika'],
            'full_name': PLANET_FULL_NAMES['gulika'],
        }
    yamaghanta_longitude = _yamaghanta_longitude(
        date_of_birth,
        time_of_birth,
        latitude,
        longitude,
        use_sidereal,
    )
    if yamaghanta_longitude is not None:
        positions['yamaghanta'] = {
            'longitude': yamaghanta_longitude,
            'rasi': rasi_name_from_longitude(yamaghanta_longitude),
            'short_name': PLANET_NAME_MAP['yamaghanta'],
            'full_name': PLANET_FULL_NAMES['yamaghanta'],
        }
    lagna_longitude = _lagna_longitude(jd_ut, latitude, longitude, use_sidereal)
    lagna = rasi_name_from_longitude(lagna_longitude)

    nakshatra_index = nakshatra_index_from_longitude(moon_longitude)
    nakshatra = NAKSHATRA_DATA[nakshatra_index]
    nakshatra_pada = nakshatra_pada_from_longitude(moon_longitude)

    _eng = str(getattr(settings, 'ASTROLOGY_ENGINE_VERSION', '1'))
    chart_basis = (
        {'zodiac': 'sidereal', 'ayanamsa': 'lahiri', 'engine_version': _eng}
        if use_sidereal
        else {'zodiac': 'tropical', 'ayanamsa': None, 'engine_version': _eng}
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


class HoroscopeService:
    """
    Chart helpers from a persisted Horoscope row (sidereal grahanila JSON).
    Planet keys in chart dicts match HoroscopeSerializer / grahanila full_name labels.
    """

    NAVAMSA_START = {
        0: 0,
        1: 9,
        2: 6,
        3: 3,
        4: 0,
        5: 9,
        6: 6,
        7: 3,
        8: 0,
        9: 9,
        10: 6,
        11: 3,
    }

    # Rasi charts: show 11 markers = Lagna + navagrahas + Gulika.
    _PLANET_ORDER = (
        'sun',
        'moon',
        'mars',
        'mercury',
        'jupiter',
        'venus',
        'saturn',
        'rahu',
        'ketu',
        'gulika',
    )

    def __init__(self, horoscope):
        self._horoscope = horoscope

    def get_lagna_longitude(self):
        g = self._horoscope.grahanila or {}
        lon = g.get('lagna_longitude')
        if lon is None:
            return None
        return float(lon)

    def get_planet_positions(self):
        """
        Sidereal longitudes from stored grahanila (Lahiri already applied at generation).
        Keys: English full names as used by chart APIs (Sun, Moon, …).
        """
        planets = (self._horoscope.grahanila or {}).get('planets') or {}
        out = {}
        for key in self._PLANET_ORDER:
            row = planets.get(key)
            if not isinstance(row, dict):
                continue
            lon = row.get('longitude')
            if lon is None:
                continue
            label = PLANET_FULL_NAMES.get(key, key.replace('_', ' ').title())
            out[label] = {'longitude': float(lon)}
        return out

    def get_rasi_chart(self):
        result = {r: [] for r in RASI_NAMES}
        positions = self.get_planet_positions()
        lagna_long = self.get_lagna_longitude()
        if lagna_long is None:
            return {}

        for planet_name, data in positions.items():
            longitude = data.get('longitude', 0.0)
            rasi_index = int(longitude / 30.0) % 12
            rasi = RASI_NAMES[rasi_index]
            result[rasi].append(planet_name)

        lagna_rasi_index = int(lagna_long / 30.0) % 12
        result[RASI_NAMES[lagna_rasi_index]].insert(0, 'Lagna')

        return {k: v for k, v in result.items() if v}

    def get_navamsa_chart(self):
        result = {r: [] for r in RASI_NAMES}
        positions = self.get_planet_positions()
        lagna_long = self.get_lagna_longitude()
        if lagna_long is None:
            return {}

        for planet_name, data in positions.items():
            longitude = data.get('longitude', 0.0)
            rasi_index = int(longitude / 30.0) % 12
            position_in_rasi = longitude % 30.0
            navamsa_pada = int(position_in_rasi / (30.0 / 9.0))
            navamsa_rasi_index = (self.NAVAMSA_START[rasi_index] + navamsa_pada) % 12
            rasi = RASI_NAMES[navamsa_rasi_index]
            result[rasi].append(planet_name)

        lagna_rasi_idx = int(lagna_long / 30.0) % 12
        lagna_pos = lagna_long % 30.0
        lagna_pada = int(lagna_pos / (30.0 / 9.0))
        lagna_navamsa_idx = (self.NAVAMSA_START[lagna_rasi_idx] + lagna_pada) % 12
        result[RASI_NAMES[lagna_navamsa_idx]].insert(0, 'Lagna')

        return {k: v for k, v in result.items() if v}

    def get_bhava_chart(self):
        result = {r: [] for r in RASI_NAMES}
        positions = self.get_planet_positions()
        lagna_long = self.get_lagna_longitude()
        if lagna_long is None:
            return {}
        lagna_rasi_index = int(lagna_long / 30.0) % 12
        result[RASI_NAMES[lagna_rasi_index]].insert(0, 'Lagna')

        for planet_name, data in positions.items():
            longitude = data.get('longitude', 0.0)
            diff = (longitude - lagna_long + 360.0) % 360.0
            house_number = int(diff / 30.0)
            house_rasi_index = (lagna_rasi_index + house_number) % 12
            rasi = RASI_NAMES[house_rasi_index]
            result[rasi].append(planet_name)

        return {k: v for k, v in result.items() if v}
