"""
Structured payloads for matrimony UI: profile cards (chart + center panel + dasa)
and match summary (poruthams + kuja / dasa sandhi / papam flags).
"""
from __future__ import annotations

from django.utils import timezone as dj_tz

from .chart_malayalam_data import NAKSHATRA_MALAYALAM
from .match_ui_copy import (
    PORUTHAM_ORDER,
    build_analysis,
    build_explanation,
    build_insights,
    build_poruthams_detailed,
    match_summary,
)
from .nakshatra_ui_labels import NAKSHATRA_UI_LABEL
from .porutham_service import calculate_porutham
from .utils import normalize_degree
from .vimshottari_service import seconds_until_mahadasha_end, vimshottari_mahadasha_state

MALEFICS = frozenset({'sun', 'mars', 'saturn', 'rahu', 'ketu'})
SANDHI_SECONDS = 90 * 86400


def _rasi_house_from_lagna(lagna_longitude: float, body_longitude: float) -> int:
    li = int(normalize_degree(lagna_longitude) // 30) % 12
    bi = int(normalize_degree(body_longitude) // 30) % 12
    return (bi - li) % 12 + 1


def kuja_dosham_horoscope(horoscope) -> bool:
    grahanila = horoscope.grahanila or {}
    lag_lon = grahanila.get('lagna_longitude')
    if lag_lon is None:
        return False
    planets = grahanila.get('planets') or {}
    mars = planets.get('mars') or {}
    mlon = mars.get('longitude')
    if mlon is None:
        return False
    h = _rasi_house_from_lagna(float(lag_lon), float(mlon))
    return h in {2, 4, 7, 8, 12}


def kendra_malefic_count_horoscope(horoscope) -> int:
    grahanila = horoscope.grahanila or {}
    lag_lon = grahanila.get('lagna_longitude')
    if lag_lon is None:
        return 0
    planets = grahanila.get('planets') or {}
    c = 0
    for key in MALEFICS:
        info = planets.get(key) or {}
        lon = info.get('longitude')
        if lon is None:
            continue
        h = _rasi_house_from_lagna(float(lag_lon), float(lon))
        if h in {1, 4, 7, 10}:
            c += 1
    return c


def role_label(gender: str) -> str:
    if gender == 'M':
        return 'Groom'
    if gender == 'F':
        return 'Bride'
    return 'Profile'


def build_person_card(profile, horoscope, chart_url: str) -> dict:
    user = profile.user
    nk = horoscope.nakshatra
    dasa = vimshottari_mahadasha_state(horoscope, ref_utc=dj_tz.now())

    center_panel = {
        'nakshatra': NAKSHATRA_UI_LABEL.get(nk, nk),
        'nakshatra_english': nk,
        'nakshatra_malayalam': NAKSHATRA_MALAYALAM.get(nk, ''),
        'padam': horoscope.nakshatra_pada,
    }
    if dasa:
        center_panel['dasa'] = {
            'lord': dasa['lord'],
            'lord_key': dasa['lord_key'],
            'remaining': dasa['remaining'],
            'remaining_label': dasa['remaining_label'],
        }
    else:
        center_panel['dasa'] = None

    nk_label = NAKSHATRA_UI_LABEL.get(nk, nk)
    padam = horoscope.nakshatra_pada
    chart_meta = {
        'lagna_label': horoscope.lagna or '',
        'rasi_label': horoscope.rasi or '',
        'nakshatra_label': nk_label,
        'display_title': f'{nk_label} ({nk}) - Pada {padam}',
    }

    return {
        'matri_id': user.matri_id or '',
        'name': (user.name or '').strip(),
        'role': role_label(getattr(user, 'gender', '') or ''),
        'profile_id': profile.pk,
        'gender': user.gender or '',
        'nakshatra': nk,
        'nakshatra_label': nk_label,
        'nakshatra_malayalam': NAKSHATRA_MALAYALAM.get(nk, ''),
        'nakshatra_pada': padam,
        'rasi': horoscope.rasi,
        'lagna': horoscope.lagna,
        'chart_url': chart_url,
        'center_panel': center_panel,
        'chart_meta': chart_meta,
        'kuja_dosham': kuja_dosham_horoscope(horoscope),
        'kendra_malefic_count': kendra_malefic_count_horoscope(horoscope),
    }


def _bride_groom_horoscopes(primary_profile, partner_profile, primary_h, partner_h):
    pg = getattr(primary_profile.user, 'gender', '') or ''
    og = getattr(partner_profile.user, 'gender', '') or ''
    if pg == 'F' and og == 'M':
        return primary_h, partner_h
    if pg == 'M' and og == 'F':
        return partner_h, primary_h
    return primary_h, partner_h


def _dasa_sandhi(primary_h, partner_h) -> bool:
    ref = dj_tz.now()
    s1 = seconds_until_mahadasha_end(primary_h, ref)
    s2 = seconds_until_mahadasha_end(partner_h, ref)
    if s1 is None or s2 is None:
        return False
    return s1 < SANDHI_SECONDS or s2 < SANDHI_SECONDS


def build_match_ui(
    primary_profile,
    partner_profile,
    primary_h,
    partner_h,
) -> dict:
    bride_h, groom_h = _bride_groom_horoscopes(
        primary_profile, partner_profile, primary_h, partner_h
    )
    por = calculate_porutham(bride_h, groom_h)
    p = por['poruthams']
    koota_points = por.get('koota_points') or {}

    kuja_b = kuja_dosham_horoscope(bride_h)
    kuja_g = kuja_dosham_horoscope(groom_h)
    kuja_matched = kuja_b == kuja_g

    sandhi = _dasa_sandhi(primary_h, partner_h)

    kb = kendra_malefic_count_horoscope(bride_h)
    kg = kendra_malefic_count_horoscope(groom_h)
    papam_ok = abs(kb - kg) <= 1

    score = por['score']
    max_score = por['max_score']
    result = por['result']
    mx = max_score if max_score else 10
    compatibility_grade = round((score / mx) * 100.0, 2) if mx else 0.0

    matched_poruthams = [k for k in PORUTHAM_ORDER if k in p and p[k]]

    analysis = build_analysis(p)
    explanation = build_explanation(
        p,
        score,
        kuja_matched,
        sandhi,
        analysis['critical_issues'],
        analysis['moderate_issues'],
    )

    return {
        'bride_matri_id': getattr(bride_h.profile.user, 'matri_id', '') or '',
        'groom_matri_id': getattr(groom_h.profile.user, 'matri_id', '') or '',
        'poruthams': p,
        'matched_poruthams': matched_poruthams,
        'score': score,
        'max_score': max_score,
        'result': result,
        'compatibility_grade': compatibility_grade,
        'summary': match_summary(score, max_score, result),
        'analysis': analysis,
        'explanation': explanation,
        'poruthams_detailed': build_poruthams_detailed(p, koota_points),
        'koota_points': koota_points,
        'insights': build_insights(p, score),
        'flags': {
            'kuja_dosham_bride': kuja_b,
            'kuja_dosham_groom': kuja_g,
            'dasa_sandhi': sandhi,
            'papam_samyam_matched': papam_ok,
            'kendra_malefic_bride': kb,
            'kendra_malefic_groom': kg,
        },
    }
