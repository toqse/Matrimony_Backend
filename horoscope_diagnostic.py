"""
Run from Django project root:
  python manage.py shell < horoscope_diagnostic.py

Prints birth time interpretation, JD_UT, ayanamsa, and Moon longitudes to debug
nakshatra boundary discrepancies (Swiss Ephemeris vs Moshier fallback).
"""

from datetime import date, time

from django.conf import settings

from astrology.services import horoscope_service as hs


def _fmt_deg(deg: float) -> str:
    d = float(deg) % 360.0
    whole = int(d)
    m_float = (d - whole) * 60.0
    minute = int(m_float)
    sec = (m_float - minute) * 60.0
    return f"{whole:03d}° {minute:02d}' {sec:05.2f}\""


def _nak_boundary_info(moon_sidereal: float) -> dict:
    seg = 360.0 / 27.0
    lon = float(moon_sidereal) % 360.0
    idx = int(lon // seg)
    start = idx * seg
    end = (idx + 1) * seg
    return {
        "nak_index": idx,
        "segment_start": start,
        "segment_end": end,
        "deg_to_end": end - lon,
        "deg_from_start": lon - start,
    }


print("Django TIME_ZONE:", getattr(settings, "TIME_ZONE", None))
print("Django USE_TZ:", getattr(settings, "USE_TZ", None))
print("SWISSEPH_EPHE_PATH:", getattr(settings, "SWISSEPH_EPHE_PATH", ""))

if getattr(hs, "swe", None) is None:
    raise SystemExit("pyswisseph not installed / failed to import")

# The boundary case mentioned in the prompt:
dob = date(1993, 8, 3)
tob = time(7, 0, 0)  # IST
pob = "Alappuzha, Kerala, India"

# Offline coords (avoid Nominatim); adjust if you want.
lat, lon = 9.5003416, 76.4123364

hs._init_ephemeris_path()
jd_ut = hs._julian_day_utc(dob, tob)

flags = hs._calc_flags(True)
ayan = float(hs.swe.get_ayanamsa_ut(jd_ut))

moon_trop = float(hs.swe.calc_ut(jd_ut, hs.swe.MOON, hs._calc_flags(False))[0][0])
moon_sid = float(hs.swe.calc_ut(jd_ut, hs.swe.MOON, flags)[0][0])

print("\nInputs:", dob, tob, pob)
print("JD_UT:", jd_ut)
print("Ayanamsa_ut:", ayan, "(", _fmt_deg(ayan), ")")
print("Moon tropical:", moon_trop, "(", _fmt_deg(moon_trop), ")")
print("Moon sidereal:", moon_sid, "(", _fmt_deg(moon_sid), ")")

nak_idx = hs.nakshatra_index_from_longitude(moon_sid)
pada = hs.nakshatra_pada_from_longitude(moon_sid)
nak_name = hs.NAKSHATRA_DATA[nak_idx]["name"]

print("Nakshatra:", nak_name, "index=", nak_idx, "pada=", pada)
bi = _nak_boundary_info(moon_sid)
print("Boundary start:", _fmt_deg(bi["segment_start"]), "end:", _fmt_deg(bi["segment_end"]))
print("Δ from start:", bi["deg_from_start"], "deg; Δ to end:", bi["deg_to_end"], "deg")

asc = hs._lagna_longitude(jd_ut, lat, lon, True)
print("Lagna sidereal:", asc, "(", _fmt_deg(asc), ") ->", hs.rasi_name_from_longitude(asc))

