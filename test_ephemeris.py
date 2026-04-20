import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'matrimony_backend.settings.development')
django.setup()

from django.conf import settings  # noqa: E402

try:
    import swisseph as swe  # noqa: E402
except Exception as exc:
    raise SystemExit(f"pyswisseph/swisseph is not installed in this environment: {exc}")

print("SWISSEPH_EPHE_PATH:", getattr(settings, 'SWISSEPH_EPHE_PATH', 'NOT SET'))

# Test with known boundary case
# Sisira: 1993-Aug-03, 07:00 AM IST = 01:30 UTC = JD 2449202.5625
JD = 2449202.5625
swe.set_sid_mode(swe.SIDM_LAHIRI)

# Test Moshier (no files)
r_moshier = swe.calc_ut(JD, swe.MOON, swe.FLG_MOSEPH | swe.FLG_SIDEREAL)
print(
    "Moon (Moshier):",
    round(r_moshier[0][0], 4),
    "→",
    "Avittam" if r_moshier[0][0] > 293.333 else "Thiruvonam",
)

# Test Swiss Ephemeris (with files)
r_sweph = swe.calc_ut(JD, swe.MOON, swe.FLG_SWIEPH | swe.FLG_SIDEREAL)
print(
    "Moon (SwissEph):",
    round(r_sweph[0][0], 4),
    "→",
    "Avittam" if r_sweph[0][0] > 293.333 else "Thiruvonam",
)

print("Difference:", round(r_sweph[0][0] - r_moshier[0][0], 4), "degrees")
print("Nakshatra boundary: 293.3333°")
print("RESULT:", "✓ FIXED — SwissEph gives Avittam" if r_sweph[0][0] > 293.333 else "✗ STILL WRONG — check ephe path")

