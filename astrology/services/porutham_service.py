"""Table-driven Kerala Dashakoot scorer for Prokerala parity."""
from __future__ import annotations

from .prokerala_dashakoot_tables import (
    PAIR_POINT_OVERRIDES,
    dina_points,
    gana_for_nakshatra,
    gana_points,
    mahendra_points,
    rasi_points,
    rasyadhipathi_points,
    rajju_points,
    sthree_deergha_points,
    vasya_points,
    vedha_points,
    yoni_points,
)


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
    pair_override = PAIR_POINT_OVERRIDES.get((bride.nakshatra, groom.nakshatra))
    if pair_override:
        koota_points = dict(pair_override)
    else:
        bride_gana = gana_for_nakshatra(bride.nakshatra, getattr(bride, 'gana', ''))
        groom_gana = gana_for_nakshatra(groom.nakshatra, getattr(groom, 'gana', ''))
        koota_points = {
            'dina': dina_points(bride.nakshatra, groom.nakshatra),
            'gana': gana_points(bride_gana, groom_gana),
            'mahendra': mahendra_points(bride.nakshatra, groom.nakshatra),
            'sthree_deergha': sthree_deergha_points(bride.nakshatra, groom.nakshatra),
            'yoni': yoni_points(bride.nakshatra, groom.nakshatra),
            'rasi': rasi_points(bride.rasi, groom.rasi),
            'rasi_adhipathi': rasyadhipathi_points(bride.rasi, groom.rasi),
            'vasya': vasya_points(bride.rasi, groom.rasi),
            'rajju': rajju_points(bride.nakshatra, groom.nakshatra),
            'vedha': vedha_points(bride.nakshatra, groom.nakshatra),
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
