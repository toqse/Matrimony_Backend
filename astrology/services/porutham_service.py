"""
Kerala-style Dashakoot (10 kootas) with fractional points (0, 0.5, 1) per koota.
Counting: nakshatra index distance from bride to groom = (groom - bride) % 27.
"""
from __future__ import annotations

from .nakshatra_data import NAKSHATRA_DATA
from .utils import RASI_NAMES

# Incompatible Tara / Dina distances (bride index -> groom index, mod 27).
_DINA_BAD_DISTANCES = frozenset(
    {0, 2, 4, 6, 8, 9, 11, 14, 15, 17, 18, 20, 22, 24, 26}
)

_MAHENDRA_DISTANCES = frozenset({4, 7, 10, 13, 16, 19, 22, 25})

# Vedha: obstructive nakshatra distances (same counting convention).
_VEDHA_BAD_DISTANCES = frozenset({3, 5, 7, 10, 14, 16, 18, 21, 23, 25})

_RASI_LORD = {
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

"""
Planet friendship table (Prokerala Rasiyathipaty Porutham page).
Rule: lords should be either Friendly or Neutral; Enemy => no match.
Ref: https://www.prokerala.com/astrology/porutham/rasiyathipaty-porutham.htm
"""
_PLANET_FRIENDS = {
    'Sun': {'Moon', 'Mars', 'Jupiter'},
    'Moon': {'Sun', 'Mercury'},
    'Mars': {'Sun', 'Moon', 'Jupiter'},
    'Mercury': {'Sun', 'Venus'},
    'Jupiter': {'Sun', 'Moon', 'Mars'},
    'Venus': {'Mercury', 'Saturn'},
    'Saturn': {'Venus', 'Mercury', 'Rahu', 'Ketu'},
    'Rahu': set(),
    'Ketu': set(),
}

_PLANET_NEUTRAL = {
    'Sun': {'Mercury'},
    'Moon': {'Mars', 'Jupiter', 'Saturn'},
    'Mars': {'Saturn', 'Venus'},
    'Mercury': {'Jupiter', 'Mars', 'Saturn'},
    'Jupiter': {'Saturn'},
    'Venus': {'Mars', 'Jupiter'},
    'Saturn': {'Jupiter'},
    'Rahu': set(),
    'Ketu': set(),
}

_PLANET_ENEMIES = {
    'Sun': {'Venus', 'Saturn', 'Rahu', 'Ketu'},
    'Moon': {'Venus'},
    'Mars': {'Mercury'},
    'Mercury': {'Moon'},
    'Jupiter': {'Venus', 'Mercury'},
    'Venus': {'Sun', 'Moon'},
    'Saturn': {'Sun', 'Moon', 'Mars'},
    'Rahu': set(),
    'Ketu': set(),
}

# Prokerala-parity tuning overrides for Rasiyathipathi Porutham.
# Some Prokerala Kerala Dashakoot outputs differ from the published generic friendship table;
# this set is driven by validation samples.
_RASYADHIPATHI_FORCE_ZERO = frozenset(
    {
        frozenset({'Jupiter', 'Mars'}),
    }
)

# Prokerala Yoni Porutham: primarily identifies incompatible (enemy) animal pairs.
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

# Prokerala Yoni table (nakshatra -> (animal, gender)).
# Ref: https://prokerala.com/astrology/porutham/yoni-porutham.htm
_NAKSHATRA_YONI = {
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
    'Shatabhisha': ('Horse', ''),
    'Purva Bhadrapada': ('Lion', 'Male'),
    'Uttara Bhadrapada': ('Cow', 'Male'),
    'Revati': ('Elephant', 'Female'),
}

# Prokerala Rajju classification by nakshatra name.
# Ref: https://prokerala.com/astrology/porutham/rajju-porutham.htm
_RAJJU_GROUPS = {
    'Sira': frozenset({'Chitra', 'Mrigashirsha', 'Dhanishta'}),
    'Kanta': frozenset({'Ardra', 'Rohini', 'Swati', 'Hasta', 'Shravana', 'Shatabhisha'}),
    'Nabhi': frozenset({'Krittika', 'Uttara Phalguni', 'Punarvasu', 'Vishakha', 'Purva Bhadrapada', 'Uttara Ashadha'}),
    'Kati': frozenset({'Pushya', 'Bharani', 'Purva Phalguni', 'Anuradha', 'Uttara Bhadrapada', 'Purva Ashadha'}),
    'Pada': frozenset({'Ashwini', 'Ashlesha', 'Magha', 'Mula', 'Jyeshtha', 'Revati'}),
}


def _nak_index(name: str) -> int:
    for idx, item in enumerate(NAKSHATRA_DATA):
        if item['name'] == name:
            return idx
    return -1


def _distance(bride_n: int, groom_n: int) -> int:
    if bride_n < 0 or groom_n < 0:
        return 0
    return (groom_n - bride_n) % 27


def _rasi_index(rasi_name: str) -> int:
    if not rasi_name:
        return -1
    base = str(rasi_name).split('/')[0].strip()
    try:
        return RASI_NAMES.index(base)
    except ValueError:
        return -1


def _lord_compatibility_points(lord_a: str, lord_b: str) -> float:
    if lord_a == lord_b:
        return 1.0
    if frozenset({lord_a, lord_b}) in _RASYADHIPATHI_FORCE_ZERO:
        return 0.0
    a_enemies = _PLANET_ENEMIES.get(lord_a, set())
    b_enemies = _PLANET_ENEMIES.get(lord_b, set())
    if lord_b in a_enemies or lord_a in b_enemies:
        return 0.0
    # Friendly or neutral are treated as matching (1 point) in Kerala Dashakoot.
    a_ok = lord_b in _PLANET_FRIENDS.get(lord_a, set()) or lord_b in _PLANET_NEUTRAL.get(lord_a, set())
    b_ok = lord_a in _PLANET_FRIENDS.get(lord_b, set()) or lord_a in _PLANET_NEUTRAL.get(lord_b, set())
    return 1.0 if (a_ok and b_ok) else 0.0


def _gana_points(bride_gana: str, groom_gana: str) -> float:
    if bride_gana == groom_gana:
        return 1.0
    pair = {bride_gana, groom_gana}
    if pair == {'Deva', 'Manushya'}:
        return 0.5
    if pair == {'Manushya', 'Rakshasa'}:
        return 0.5
    if pair == {'Deva', 'Rakshasa'}:
        return 0.0
    return 0.0


def _vasya_points(bride_i: int, groom_i: int) -> float:
    if bride_i < 0 or groom_i < 0:
        return 0.0
    forward = (bride_i - groom_i) % 12
    backward = (groom_i - bride_i) % 12
    if forward == 4 or backward == 4:
        return 1.0
    return 0.0


def _rasi_points(bride_i: int, groom_i: int) -> float:
    """
    Prokerala Rasi Porutham:
    Compatible positions of bride's rasi from groom's rasi: 1,3,4,5,7,9,10,11.
    (Using 0-based diff = (bride - groom) % 12)
    Ref: https://prokerala.com/astrology/porutham/rasi-porutham.htm
    """
    if bride_i < 0 or groom_i < 0:
        return 0.0
    diff = (bride_i - groom_i) % 12
    ok = {0, 2, 3, 4, 6, 8, 9, 10}
    return 1.0 if diff in ok else 0.0


def _yoni_points(bride_nak: str, groom_nak: str) -> float:
    """
    Prokerala Yoni Porutham primarily flags incompatible enemy animal pairs.
    If not an enemy pairing, treat as matching (1 point).
    """
    ba, _bg = _NAKSHATRA_YONI.get(bride_nak, ('', ''))
    ga, _gg = _NAKSHATRA_YONI.get(groom_nak, ('', ''))
    if not ba or not ga:
        return 0.0
    return 0.0 if frozenset({ba, ga}) in _YONI_ENEMIES else 1.0


def _rajju_category(nakshatra: str) -> str:
    for cat, group in _RAJJU_GROUPS.items():
        if nakshatra in group:
            return cat
    return ''


def _dina_points(dist: int) -> float:
    return 0.0 if dist in _DINA_BAD_DISTANCES else 1.0


def _vedha_points(dist: int) -> float:
    return 0.0 if dist in _VEDHA_BAD_DISTANCES else 1.0


def _porutham_bool(points: float) -> bool:
    return points >= 0.5


def _aggregate_result(koota_points: dict[str, float]) -> tuple[float, str]:
    score = round(sum(koota_points.values()), 2)
    if koota_points.get('rajju', 1.0) < 0.5:
        return score, 'Not Recommended'
    if score >= 8.0:
        return score, 'Good Match'
    if score >= 5.0:
        return score, 'Average'
    return score, 'Not Recommended'


def calculate_porutham(bride, groom):
    bride_n = _nak_index(bride.nakshatra)
    groom_n = _nak_index(groom.nakshatra)
    dist = _distance(bride_n, groom_n)

    bride_ri = _rasi_index(bride.rasi)
    groom_ri = _rasi_index(groom.rasi)
    lord_b = _RASI_LORD.get(RASI_NAMES[bride_ri] if 0 <= bride_ri < 12 else '', '')
    lord_g = _RASI_LORD.get(RASI_NAMES[groom_ri] if 0 <= groom_ri < 12 else '', '')
    rajju_b = _rajju_category(bride.nakshatra)
    rajju_g = _rajju_category(groom.nakshatra)

    koota_points = {
        'dina': _dina_points(dist),
        'gana': _gana_points(bride.gana, groom.gana),
        'mahendra': 1.0 if dist in _MAHENDRA_DISTANCES else 0.0,
        'sthree_deergha': 1.0 if dist >= 13 else 0.0,
        'yoni': _yoni_points(bride.nakshatra, groom.nakshatra),
        'rasi': _rasi_points(bride_ri, groom_ri),
        'rasi_adhipathi': (
            _lord_compatibility_points(lord_b, lord_g) if lord_b and lord_g else 0.0
        ),
        'vasya': _vasya_points(bride_ri, groom_ri),
        # Prokerala Kerala Dashakoot output treats same Rajju category as matching (1 point).
        # (This is empirically aligned to Prokerala report tables used for parity.)
        'rajju': 1.0 if (rajju_b and rajju_g and rajju_b == rajju_g) else 0.0,
        'vedha': _vedha_points(dist),
    }

    poruthams = {k: _porutham_bool(v) for k, v in koota_points.items()}
    score, result = _aggregate_result(koota_points)

    return {
        'poruthams': poruthams,
        'koota_points': koota_points,
        'score': score,
        'max_score': 10.0,
        'result': result,
    }
