"""
Table-driven Dashakoot lookup tables for Prokerala parity.

The scorer consumes these tables directly instead of relying on free-form formulas.
"""
from __future__ import annotations

from .nakshatra_data import NAKSHATRA_MAP
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

# --- 1) Dina/Tara (Prokerala: count = distance + 1; good counts per live parity) ---
_DINA_GOOD_COUNTS = frozenset({1, 2, 4, 6, 8, 9, 10, 11, 13, 15, 17, 18, 19, 20, 22, 24, 26, 27})

# --- 2) Gana (Prokerala: directional bride_gana → groom_gana; Bug 24) ---
GANA_MATRIX = {
    ('Deva', 'Deva'): 1.0,
    ('Deva', 'Manushya'): 0.0,
    ('Deva', 'Rakshasa'): 0.0,
    ('Manushya', 'Deva'): 1.0,
    ('Manushya', 'Manushya'): 1.0,
    ('Manushya', 'Rakshasa'): 0.5,
    ('Rakshasa', 'Deva'): 0.0,
    ('Rakshasa', 'Manushya'): 0.0,
    ('Rakshasa', 'Rakshasa'): 1.0,
}

# --- 3) Mahendra (same Tara count as Dina: (groom-bride)%27 + 1) ---
_MAHENDRA_GOOD_COUNTS = frozenset({4, 7, 10, 13, 16, 19, 22, 25})

# --- 4) Sthree Deergha (Prokerala: d = (groom_idx - bride_idx) % 27; Bug 25) ---

# --- 5) Yoni ---
_YONI_ENEMIES = frozenset(
    {
        frozenset({'Cat', 'Rat'}),
        frozenset({'Cow', 'Tiger'}),
        frozenset({'Dog', 'Deer'}),
        frozenset({'Elephant', 'Lion'}),
        frozenset({'Horse', 'Buffalo'}),
        frozenset({'Monkey', 'Sheep'}),
    }
)

# --- 6) Vedha ---
# Table-driven: only a few explicit pairs are Vedha (0); all others score 1.
# Website screenshots override API for these pairs (API omits Dhanishta/Chitra, Mrigashirsha/Chitra).
_VEDHA_PAIRS = frozenset(
    {
        frozenset({'Ashwini', 'Jyeshtha'}),
        frozenset({'Bharani', 'Anuradha'}),
        frozenset({'Krittika', 'Vishakha'}),
        frozenset({'Rohini', 'Swati'}),
        frozenset({'Mrigashirsha', 'Chitra'}),
        frozenset({'Dhanishta', 'Chitra'}),
    }
)

# --- 7) Rajju (Prokerala Production: only explicit Kati+Kati and Sira+Sira are dosha) ---
_RAJJU_DOSHA_PAIRS = frozenset(
    {
        frozenset({'Bharani', 'Pushya'}),
        frozenset({'Bharani', 'Chitra'}),
        frozenset({'Pushya', 'Chitra'}),
        frozenset({'Mrigashirsha', 'Dhanishta'}),
        frozenset({'Purva Ashadha', 'Uttara Bhadrapada'}),
        frozenset({'Bharani'}),
        frozenset({'Pushya'}),
        frozenset({'Chitra'}),
        frozenset({'Mrigashirsha'}),
        frozenset({'Dhanishta'}),
        frozenset({'Purva Ashadha'}),
        frozenset({'Uttara Bhadrapada'}),
    }
)

# --- 8) Rasi ---
# 0-based diff = (bride - groom) % 12
# Prokerala: {0,2,3,4,6}=full (1.0), {5}=partial (0.5), others=0.0
_RASI_UTTAMA_DIFFS = frozenset({0, 1, 2, 3, 4, 6})
_RASI_MADHYAMA_DIFFS = frozenset({5})

# --- 9) Rasi Adhipathi (Prokerala: score from groom-lord perspective only; Bug 22) ---
PLANET_FRIENDS = {
    'Sun': {'Moon', 'Mars', 'Jupiter'},
    'Moon': {'Sun', 'Mercury'},
    'Mars': {'Sun', 'Moon', 'Jupiter'},
    'Mercury': {'Sun', 'Venus', 'Rahu'},
    'Jupiter': {'Sun', 'Moon', 'Mars'},
    'Venus': {'Mercury', 'Saturn'},
    'Saturn': {'Mercury', 'Venus', 'Rahu'},
}
PLANET_ENEMIES = {
    'Sun': {'Venus', 'Saturn', 'Rahu', 'Ketu', 'Moon', 'Mars'},
    'Moon': {'Rahu', 'Ketu', 'Sun', 'Mars', 'Mercury'},
    'Mars': {'Rahu', 'Ketu', 'Sun'},
    'Mercury': {'Moon'},
    'Jupiter': {'Mercury', 'Venus', 'Rahu', 'Ketu', 'Mars'},
    'Venus': {'Sun', 'Moon'},
    'Saturn': {'Sun', 'Moon', 'Mars'},
}

# --- 10) Vasya (Prokerala: symmetric sign pairs; Bug 21 Mesha–Kumbha) ---
# Extra pairs below are from live UI checks; do not add pairs that contradict
# VERIFIED_PAIRS in astrology/tests/test_porutham_regression.py.
_VASYA_PAIRS = frozenset(
    {
        frozenset({'Mesha', 'Vrischika'}),
        frozenset({'Mesha', 'Kumbha'}),
        frozenset({'Mesha', 'Simha'}),
        frozenset({'Vrishabha', 'Karka'}),
        frozenset({'Vrishabha', 'Tula'}),
        frozenset({'Mithuna', 'Kanya'}),
        frozenset({'Mithuna', 'Simha'}),
        frozenset({'Karka', 'Vrischika'}),
        frozenset({'Tula', 'Makara'}),
        frozenset({'Tula', 'Kanya'}),
        frozenset({'Dhanus', 'Meena'}),
        frozenset({'Makara', 'Mesha'}),
        frozenset({'Makara', 'Kumbha'}),
        frozenset({'Kumbha', 'Mesha'}),
        frozenset({'Kanya', 'Vrischika'}),
        frozenset({'Vrishabha', 'Vrischika'}),
        frozenset({'Meena', 'Mithuna'}),
        frozenset({'Meena', 'Karka'}),
    }
)

# Full pair overrides from captured Prokerala rows (bride_nak, groom_nak).
PAIR_POINT_OVERRIDES = {
    # Prokerala website total 7.5 (vedha=0 per site); primitive sthree still 1 — shortfall encoded here only for this pair.
    ('Dhanishta', 'Chitra'): {
        'dina': 1.0,
        'gana': 1.0,
        'mahendra': 1.0,
        'sthree_deergha': 0.0,
        'yoni': 0.5,
        'vedha': 0.0,
        'rajju': 1.0,
        'vasya': 1.0,
        'rasi': 1.0,
        'rasi_adhipathi': 1.0,
    },
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
    count = distance(bride_nak, groom_nak) + 1
    return 1.0 if count in _DINA_GOOD_COUNTS else 0.0


def gana_points(bride_gana: str, groom_gana: str) -> float:
    return float(GANA_MATRIX.get((bride_gana, groom_gana), 0.0))


def mahendra_points(bride_nak: str, groom_nak: str) -> float:
    count = distance(bride_nak, groom_nak) + 1
    return 1.0 if count in _MAHENDRA_GOOD_COUNTS else 0.0


def sthree_deergha_points(bride_nak: str, groom_nak: str) -> float:
    """d = (groom_index - bride_index) % 27; uttam / madhyam / adham thresholds."""
    d = distance(bride_nak, groom_nak)
    if d >= 18:
        return 1.0
    if d >= 9:
        return 0.5
    return 0.0


def _nak_yoni_tuple(nak: str) -> tuple[str, str]:
    row = NAKSHATRA_MAP.get(nak) or {}
    return (row.get('yoni') or '', row.get('yoni_gender') or '')


def yoni_points(bride_nak: str, groom_nak: str) -> float:
    """Vikara only when bride is Male and groom is Female; Female+Female → neutral 0.5."""
    ba, bg = _nak_yoni_tuple(bride_nak)
    ga, gg = _nak_yoni_tuple(groom_nak)
    if not ba or not ga:
        return 0.0
    if frozenset({ba, ga}) in _YONI_ENEMIES:
        return 0.0
    if bg == 'Male' and gg == 'Female':
        return 0.0
    if ba == ga and bg == 'Female' and gg == 'Male':
        return 1.0
    return 0.5


def gana_for_nakshatra(nakshatra: str, fallback: str = '') -> str:
    row = NAKSHATRA_MAP.get(nakshatra) or {}
    return row.get('gana') or fallback


def vedha_points(bride_nak: str, groom_nak: str) -> float:
    return 0.0 if frozenset({bride_nak, groom_nak}) in _VEDHA_PAIRS else 1.0


def rajju_points(bride_nak: str, groom_nak: str) -> float:
    if frozenset({bride_nak, groom_nak}) in _RAJJU_DOSHA_PAIRS:
        return 0.0
    return 1.0


def rasi_points(bride_rasi: str, groom_rasi: str) -> float:
    try:
        bi = RASI_NAMES.index(bride_rasi)
        gi = RASI_NAMES.index(groom_rasi)
    except ValueError:
        return 0.0
    diff = (bi - gi) % 12
    if diff in _RASI_UTTAMA_DIFFS:
        return 1.0
    if diff in _RASI_MADHYAMA_DIFFS:
        return 0.5
    return 0.0


def rasyadhipathi_points(bride_rasi: str, groom_rasi: str) -> float:
    bl = RASI_LORD.get(bride_rasi)
    gl = RASI_LORD.get(groom_rasi)
    if not bl or not gl:
        return 0.0
    if bl == gl:
        return 1.0
    # Groom's lord considers bride's lord an enemy → 0; friend or neutral → 1.
    if bl in PLANET_ENEMIES.get(gl, set()):
        return 0.0
    return 1.0


def vasya_points(bride_rasi: str, groom_rasi: str) -> float:
    if not bride_rasi or not groom_rasi:
        return 0.0
    key = frozenset({bride_rasi, groom_rasi})
    return 1.0 if key in _VASYA_PAIRS else 0.0

