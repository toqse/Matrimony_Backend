from .nakshatra_data import NAKSHATRA_DATA


def _nak_index(name: str) -> int:
    for idx, item in enumerate(NAKSHATRA_DATA):
        if item['name'] == name:
            return idx
    return -1


def _distance(a: int, b: int) -> int:
    if a < 0 or b < 0:
        return 0
    return (b - a) % 27


def calculate_porutham(bride, groom):
    bride_n = _nak_index(bride.nakshatra)
    groom_n = _nak_index(groom.nakshatra)
    dist = _distance(bride_n, groom_n)

    poruthams = {
        'dina': dist not in {0, 1, 2, 3, 4, 5, 7, 9},
        'gana': bride.gana == groom.gana or {'Deva', 'Manushya'} == {bride.gana, groom.gana},
        'mahendra': dist in {4, 7, 10, 13, 16, 19, 22, 25},
        'sthree_deergha': dist >= 13,
        'yoni': bride.yoni == groom.yoni,
        'rasi': bride.rasi != groom.rasi,
        'rasi_adhipathi': bride.rasi != groom.rasi or bride.gana == groom.gana,
        'vasya': bride.rasi == groom.rasi or bride.gana == groom.gana,
        'rajju': bride.rajju != groom.rajju,
        'vedha': dist not in {3, 5, 7, 10, 14, 16, 18, 21, 23, 25},
    }

    score = sum(1 for value in poruthams.values() if value)
    if poruthams['rajju'] is False:
        result = 'Not Recommended'
    elif score >= 8:
        result = 'Good Match'
    elif score >= 5:
        result = 'Average'
    else:
        result = 'Not Recommended'

    return {
        'poruthams': poruthams,
        'score': score,
        'max_score': 10,
        'result': result,
    }
