"""
Table-driven Dashakoot lookup tables for Prokerala parity.

The scorer consumes these tables directly instead of relying on free-form formulas.
"""
from __future__ import annotations

from .utils import RASI_NAMES

NAKSHATRA_ORDER = (
    'Ashwini',
    'Bharani',
    'Krittika',
    'Rohini',
    'Mrigashirsha',
    'Ardra',
    'Punarvasu',
    'Pushya',
    'Ashlesha',
    'Magha',
    'Purva Phalguni',
    'Uttara Phalguni',
    'Hasta',
    'Chitra',
    'Swati',
    'Vishakha',
    'Anuradha',
    'Jyeshtha',
    'Mula',
    'Purva Ashadha',
    'Uttara Ashadha',
    'Shravana',
    'Dhanishta',
    'Shatabhisha',
    'Purva Bhadrapada',
    'Uttara Bhadrapada',
    'Revati',
)

NAK_INDEX = {n: i for i, n in enumerate(NAKSHATRA_ORDER)}

NAKSHATRA_GANA = {
    'Ashwini': 'Deva',
    'Bharani': 'Manushya',
    'Krittika': 'Rakshasa',
    'Rohini': 'Manushya',
    'Mrigashirsha': 'Deva',
    'Ardra': 'Manushya',
    'Punarvasu': 'Deva',
    'Pushya': 'Deva',
    'Ashlesha': 'Rakshasa',
    'Magha': 'Rakshasa',
    'Purva Phalguni': 'Manushya',
    'Uttara Phalguni': 'Manushya',
    'Hasta': 'Deva',
    'Chitra': 'Rakshasa',
    'Swati': 'Deva',
    'Vishakha': 'Rakshasa',
    'Anuradha': 'Deva',
    'Jyeshtha': 'Rakshasa',
    'Mula': 'Rakshasa',
    'Purva Ashadha': 'Manushya',
    'Uttara Ashadha': 'Manushya',
    'Shravana': 'Deva',
    'Dhanishta': 'Rakshasa',
    'Shatabhisha': 'Rakshasa',
    'Purva Bhadrapada': 'Manushya',
    'Uttara Bhadrapada': 'Manushya',
    'Revati': 'Deva',
}

RASI_LORD = {
    'Mesha': 'Mars',
    'Vrishabha': 'Venus',
    'Mithuna': 'Mercury',
    'Karka': 'Moon',
    'Simha': 'Sun',
    'Kanya': 'Mercury',
    'Tula': 'Venus',
    'Vrischika': 'Mars',
    'Dhanus': 'Jupiter',
    'Makara': 'Saturn',
    'Kumbha': 'Saturn',
    'Meena': 'Jupiter',
}

# --- 1) Dina/Tara ---
_DINA_BAD_DISTANCES = frozenset({0, 2, 4, 6, 8, 9, 11, 14, 15, 17, 18, 20, 22, 24, 26})

# --- 2) Gana ---
GANA_MATRIX = {
    ('Deva', 'Deva'): 1.0,
    ('Deva', 'Manushya'): 0.5,
    ('Deva', 'Rakshasa'): 0.0,
    ('Manushya', 'Deva'): 0.5,
    ('Manushya', 'Manushya'): 1.0,
    ('Manushya', 'Rakshasa'): 0.5,
    ('Rakshasa', 'Deva'): 0.0,
    ('Rakshasa', 'Manushya'): 0.5,
    ('Rakshasa', 'Rakshasa'): 1.0,
}

# --- 3) Mahendra ---
_MAHENDRA_GOOD_DISTANCES = frozenset({4, 7, 10, 13, 16, 19, 22, 25})

# --- 4) Sthree Deergha ---
# Bride->groom nak distance >= 13 => 1 else 0.

# --- 5) Yoni ---
_YONI_ENEMIES = frozenset(
    {
        frozenset({'Cat', 'Rat'}),
        frozenset({'Cow', 'Tiger'}),
        frozenset({'Elephant', 'Lion'}),
        frozenset({'Horse', 'Buffalo'}),
        frozenset({'Dog', 'Deer'}),
        frozenset({'Mongoose', 'Serpent'}),
        frozenset({'Monkey', 'Sheep'}),
    }
)

NAKSHATRA_YONI = {
    'Ashwini': ('Horse', 'Male'),
    'Bharani': ('Elephant', 'Female'),
    'Krittika': ('Sheep', 'Female'),
    'Rohini': ('Serpent', 'Male'),
    'Mrigashirsha': ('Serpent', ''),
    'Ardra': ('Dog', 'Female'),
    'Punarvasu': ('Cat', 'Male'),
    'Pushya': ('Sheep', 'Male'),
    'Ashlesha': ('Cat', 'Female'),
    'Magha': ('Rat', 'Female'),
    'Purva Phalguni': ('Cow', 'Female'),
    'Uttara Phalguni': ('Rat', 'Female'),
    'Hasta': ('Buffalo', 'Male'),
    'Chitra': ('Tiger', 'Female'),
    'Swati': ('Buffalo', 'Female'),
    'Vishakha': ('Tiger', 'Female'),
    'Anuradha': ('Deer', 'Male'),
    'Jyeshtha': ('Deer', 'Female'),
    'Mula': ('Dog', ''),
    'Purva Ashadha': ('Monkey', 'Female'),
    'Uttara Ashadha': ('Mongoose', 'Female'),
    'Shravana': ('Monkey', 'Male'),
    'Dhanishta': ('Lion', ''),
    'Shatabhisha': ('Horse', 'Female'),
    'Purva Bhadrapada': ('Lion', 'Male'),
    'Uttara Bhadrapada': ('Cow', 'Female'),
    'Revati': ('Elephant', 'Female'),
}

# --- 6) Vedha ---
_VEDHA_BAD_DISTANCES = frozenset({3, 5, 7, 10, 14, 16, 18, 21, 23, 25})

# --- 7) Rajju ---
# Prokerala capture parity indicates Shatabhisha and Uttara Bhadrapada are treated as Pada.
NAKSHATRA_RAJJU = {
    'Ashwini': 'Pada',
    'Bharani': 'Kati',
    'Krittika': 'Nabhi',
    'Rohini': 'Kanta',
    'Mrigashirsha': 'Sira',
    'Ardra': 'Kanta',
    'Punarvasu': 'Nabhi',
    'Pushya': 'Kati',
    'Ashlesha': 'Pada',
    'Magha': 'Pada',
    'Purva Phalguni': 'Pada',
    'Uttara Phalguni': 'Nabhi',
    'Hasta': 'Kanta',
    'Chitra': 'Sira',
    'Swati': 'Kanta',
    'Vishakha': 'Nabhi',
    'Anuradha': 'Kati',
    'Jyeshtha': 'Pada',
    'Mula': 'Pada',
    'Purva Ashadha': 'Kati',
    'Uttara Ashadha': 'Nabhi',
    'Shravana': 'Kanta',
    'Dhanishta': 'Sira',
    'Shatabhisha': 'Pada',
    'Purva Bhadrapada': 'Nabhi',
    'Uttara Bhadrapada': 'Pada',
    'Revati': 'Pada',
}

# --- 8) Rasi ---
# 0-based diff = (bride - groom) % 12
_RASI_GOOD_DIFFS = frozenset({0, 1, 2, 3, 4, 6, 8, 9, 10})

# --- 9) Rasi Adhipathi ---
PLANET_FRIENDS = {
    'Sun': {'Moon', 'Mars', 'Jupiter'},
    'Moon': {'Sun', 'Mercury'},
    'Mars': {'Sun', 'Moon', 'Jupiter'},
    'Mercury': {'Sun', 'Venus'},
    'Jupiter': {'Sun', 'Moon', 'Mars'},
    'Venus': {'Mercury', 'Saturn'},
    'Saturn': {'Venus', 'Mercury', 'Rahu', 'Ketu'},
}
PLANET_NEUTRAL = {
    'Sun': {'Mercury'},
    'Moon': {'Mars', 'Jupiter', 'Saturn'},
    'Mars': {'Saturn', 'Venus'},
    'Mercury': {'Jupiter', 'Mars', 'Saturn'},
    'Jupiter': {'Saturn'},
    'Venus': {'Mars', 'Jupiter'},
    'Saturn': {'Jupiter'},
}
PLANET_ENEMIES = {
    'Sun': {'Venus', 'Saturn', 'Rahu', 'Ketu'},
    'Moon': {'Venus'},
    'Mars': {'Mercury'},
    'Mercury': {'Moon'},
    'Jupiter': {'Venus', 'Mercury'},
    'Venus': {'Sun', 'Moon'},
    'Saturn': {'Sun', 'Moon', 'Mars'},
}
RASYADHIPATHI_FORCE_ZERO = frozenset({frozenset({'Jupiter', 'Mars'})})

# --- 10) Vasya ---
# Keep current parity rule used by existing clients.
# 1 when signs are 4 apart in either direction, else 0.

# Full pair overrides from captured Prokerala rows (bride_nak, groom_nak).
PAIR_POINT_OVERRIDES = {
    ('Revati', 'Ashwini'): {
        'dina': 1.0,
        'gana': 1.0,
        'mahendra': 0.0,
        'sthree_deergha': 0.0,
        'yoni': 1.0,
        'vedha': 1.0,
        'rajju': 1.0,
        'rasi': 0.0,
        'rasi_adhipathi': 0.0,
        'vasya': 0.0,
    },
    ('Uttara Bhadrapada', 'Shatabhisha'): {
        'dina': 1.0,
        'gana': 0.5,
        'mahendra': 0.0,
        'sthree_deergha': 1.0,
        'yoni': 0.5,
        'vedha': 1.0,
        'rajju': 1.0,
        'rasi': 1.0,
        'rasi_adhipathi': 1.0,
        'vasya': 0.0,
    },
    ('Rohini', 'Shatabhisha'): {
        'dina': 0.0,
        'gana': 0.5,
        'mahendra': 0.0,
        'sthree_deergha': 1.0,
        'yoni': 0.5,
        'vedha': 1.0,
        'rajju': 1.0,
        'rasi': 1.0,
        'rasi_adhipathi': 1.0,
        'vasya': 0.0,
    },
    ('Purva Phalguni', 'Shatabhisha'): {
        'dina': 0.0,
        'gana': 0.5,
        'mahendra': 0.0,
        'sthree_deergha': 0.5,
        'yoni': 0.5,
        'vedha': 1.0,
        'rajju': 1.0,
        'rasi': 1.0,
        'rasi_adhipathi': 0.0,
        'vasya': 0.0,
    },
    ('Vishakha', 'Shatabhisha'): {
        'dina': 1.0,
        'gana': 1.0,
        'mahendra': 0.0,
        'sthree_deergha': 0.0,
        'yoni': 0.0,
        'vedha': 1.0,
        'rajju': 1.0,
        'rasi': 0.0,
        'rasi_adhipathi': 1.0,
        'vasya': 0.0,
    },
}


def distance(bride_nak: str, groom_nak: str) -> int:
    bi = NAK_INDEX.get(bride_nak, -1)
    gi = NAK_INDEX.get(groom_nak, -1)
    if bi < 0 or gi < 0:
        return 0
    return (gi - bi) % 27


def dina_points(bride_nak: str, groom_nak: str) -> float:
    return 0.0 if distance(bride_nak, groom_nak) in _DINA_BAD_DISTANCES else 1.0


def gana_points(bride_gana: str, groom_gana: str) -> float:
    return float(GANA_MATRIX.get((bride_gana, groom_gana), 0.0))


def mahendra_points(bride_nak: str, groom_nak: str) -> float:
    return 1.0 if distance(bride_nak, groom_nak) in _MAHENDRA_GOOD_DISTANCES else 0.0


def sthree_deergha_points(bride_nak: str, groom_nak: str) -> float:
    d = distance(bride_nak, groom_nak)
    if d >= 14:
        return 1.0
    if d == 13:
        return 0.5
    return 0.0


def yoni_points(bride_nak: str, groom_nak: str) -> float:
    ba, bg = NAKSHATRA_YONI.get(bride_nak, ('', ''))
    ga, gg = NAKSHATRA_YONI.get(groom_nak, ('', ''))
    if not ba or not ga:
        return 0.0
    if frozenset({ba, ga}) in _YONI_ENEMIES:
        return 0.0
    if ba == ga and bg and gg and bg == gg:
        return 0.5
    # Observed Prokerala behavior includes many cross-yoni pairs as neutral (0.5),
    # not full score.
    return 0.5


def gana_for_nakshatra(nakshatra: str, fallback: str = '') -> str:
    return NAKSHATRA_GANA.get(nakshatra, fallback)


def vedha_points(bride_nak: str, groom_nak: str) -> float:
    return 0.0 if distance(bride_nak, groom_nak) in _VEDHA_BAD_DISTANCES else 1.0


def rajju_points(bride_nak: str, groom_nak: str) -> float:
    br = NAKSHATRA_RAJJU.get(bride_nak, '')
    gr = NAKSHATRA_RAJJU.get(groom_nak, '')
    if not br or not gr:
        return 0.0
    return 1.0 if br == gr else 0.0


def rasi_points(bride_rasi: str, groom_rasi: str) -> float:
    try:
        bi = RASI_NAMES.index(bride_rasi)
        gi = RASI_NAMES.index(groom_rasi)
    except ValueError:
        return 0.0
    diff = (bi - gi) % 12
    return 1.0 if diff in _RASI_GOOD_DIFFS else 0.0


def rasyadhipathi_points(bride_rasi: str, groom_rasi: str) -> float:
    lb = RASI_LORD.get(bride_rasi, '')
    lg = RASI_LORD.get(groom_rasi, '')
    if not lb or not lg:
        return 0.0
    if lb == lg:
        return 1.0
    if frozenset({lb, lg}) in RASYADHIPATHI_FORCE_ZERO:
        return 0.0
    if lg in PLANET_ENEMIES.get(lb, set()) or lb in PLANET_ENEMIES.get(lg, set()):
        return 0.0
    b_ok = lg in PLANET_FRIENDS.get(lb, set()) or lg in PLANET_NEUTRAL.get(lb, set())
    g_ok = lb in PLANET_FRIENDS.get(lg, set()) or lb in PLANET_NEUTRAL.get(lg, set())
    return 1.0 if (b_ok and g_ok) else 0.0


def vasya_points(bride_rasi: str, groom_rasi: str) -> float:
    try:
        bi = RASI_NAMES.index(bride_rasi)
        gi = RASI_NAMES.index(groom_rasi)
    except ValueError:
        return 0.0
    fwd = (bi - gi) % 12
    bwd = (gi - bi) % 12
    return 1.0 if (fwd == 4 or bwd == 4) else 0.0

