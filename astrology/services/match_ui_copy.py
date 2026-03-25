"""Static copy, labels, and UI config for match/compatibility API responses."""
from __future__ import annotations

# Order matches porutham_service.calculate_porutham keys (canonical 10).
PORUTHAM_ORDER: tuple[str, ...] = (
    'dina',
    'gana',
    'mahendra',
    'sthree_deergha',
    'yoni',
    'rasi',
    'rasi_adhipathi',
    'vasya',
    'rajju',
    'vedha',
)

PORUTHAM_LABEL: dict[str, str] = {
    'dina': 'Dinam',
    'gana': 'Ganam',
    'mahendra': 'Mahendra',
    'sthree_deergha': 'Deergham',
    'yoni': 'Yoni',
    'rasi': 'Rasi',
    'rasi_adhipathi': 'Rasyadhip',
    'vasya': 'Vasyam',
    'rajju': 'Rajju Dosham',
    'vedha': 'Vedham',
}

# Reasons when this porutham *failed* (matched is False).
ANALYSIS_REASON: dict[str, str] = {
    'rajju': 'Rajju dosham may affect long-term marital stability',
    'gana': 'Ganam mismatch suggests different temperaments that may need patience',
    'yoni': 'Yoni porutham failed—inborn compatibility and rapport may be harder to build',
    'dina': 'Dinam is weak—day-to-day harmony and vitality alignment may suffer',
    'mahendra': 'Mahendra porutham failed—prosperity and lineage blessings are less assured',
    'sthree_deergha': 'Deergham (sthree deergha) did not pass—traditionally stresses bride’s well-being',
    'vedha': 'Vedham between nakshatras creates obstruction in this pairing',
    'vasya': 'Vasyam failed—mutual attraction or “who leads” may feel unbalanced',
    'rasi': 'Rasi porutham did not pass for the moon signs compared here',
    'rasi_adhipathi': 'Rasyadhip porutham failed—rasi lords do not align favorably',
}

PORUTHAM_DESCRIPTION: dict[str, str] = {
    'dina': 'Affects day-to-day compatibility and health harmony',
    'gana': 'Compares temperament (Deva / Manushya / Rakshasa)',
    'mahendra': 'Favors prosperity and continuation of lineage',
    'sthree_deergha': 'Favors long life and well-being of the bride',
    'yoni': 'Compares animal signs for instinctive harmony',
    'rasi': 'Moon sign relationship between charts',
    'rasi_adhipathi': 'Relationship between rasi lords',
    'vasya': 'Mutual attraction and who influences whom',
    'rajju': 'Body segment (rajju) compatibility; critical for overall stability',
    'vedha': 'Obstructive pairs between nakshatras',
}

PORUTHAM_SEVERITY: dict[str, str] = {
    'rajju': 'high',
    'gana': 'medium',
    'yoni': 'medium',
}


def porutham_severity(key: str) -> str:
    return PORUTHAM_SEVERITY.get(key, 'low')


def match_summary(score: float | int, max_score: float | int, result: str) -> dict:
    mx = float(max_score) if max_score else 10.0
    sc = float(score)
    pct = round((sc / mx) * 100.0, 2) if mx else 0.0
    if sc <= 3:
        grade, color_code = 'Poor', 'red'
    elif sc <= 6:
        grade, color_code = 'Average', 'orange'
    else:
        grade, color_code = 'Good', 'green'
    return {
        'score': sc,
        'max_score': mx,
        'percentage': pct,
        'result': result,
        'grade': grade,
        'color_code': color_code,
    }


def _issue(key: str) -> dict:
    return {
        'key': key,
        'label': PORUTHAM_LABEL.get(key, key),
        'reason': ANALYSIS_REASON.get(key, 'Compatibility concern'),
    }


def build_analysis(p: dict) -> dict:
    critical = []
    moderate = []
    minor = []
    if not p.get('rajju'):
        critical.append(_issue('rajju'))
    if not p.get('gana'):
        moderate.append(_issue('gana'))
    if not p.get('yoni'):
        moderate.append(_issue('yoni'))
    for key in ('dina', 'mahendra', 'sthree_deergha', 'vedha', 'vasya'):
        if not p.get(key):
            minor.append(_issue(key))
    return {
        'critical_issues': critical,
        'moderate_issues': moderate,
        'minor_issues': minor,
    }


def build_poruthams_detailed(p: dict, koota_points: dict | None = None) -> list[dict]:
    out = []
    kp = koota_points or {}
    for key in PORUTHAM_ORDER:
        if key not in p:
            continue
        row = {
            'key': key,
            'label': PORUTHAM_LABEL.get(key, key),
            'matched': bool(p[key]),
            'severity': porutham_severity(key),
            'is_critical': key == 'rajju',
            'description': PORUTHAM_DESCRIPTION.get(key, ''),
        }
        if key in kp:
            row['points'] = float(kp[key])
        out.append(row)
    return out


def build_explanation(
    p: dict,
    score: float | int,
    kuja_matched: bool,
    sandhi: bool,
    critical: list,
    moderate: list,
) -> dict:
    positives = []
    if kuja_matched:
        positives.append(
            'Kuja (Mars) dosham pattern matches on both charts—no opposing Mars stress between partners'
        )
    if p.get('rasi'):
        positives.append('Moon-sign pairing clears the Rasi porutham rule used in this report')
    if not sandhi:
        positives.append(
            'Neither side is at the edge of a major Vimshottari mahadasha change (dasa sandhi) right now'
        )

    negatives = []
    seen = set()
    for item in critical + moderate:
        k = item['key']
        if k not in seen:
            seen.add(k)
            negatives.append(item['reason'])

    if not p.get('rajju'):
        overall = (
            'Rajju dosham is present—this is treated as the most serious traditional concern. '
            'Proceed only after discussion with a qualified astrologer.'
        )
    elif float(score) <= 3:
        overall = (
            'Several core poruthams failed; overall score is low. This pairing is usually not recommended '
            'without remedial guidance.'
        )
    elif float(score) <= 6:
        overall = (
            'Mixed results: some poruthams pass but enough fail that you should weigh each concern '
            'before deciding.'
        )
    else:
        overall = (
            'Most poruthams pass; any remaining gaps are secondary and can be reviewed for peace of mind.'
        )

    return {'overall': overall, 'positives': positives, 'negatives': negatives}


def build_insights(p: dict, score: float | int) -> list[str]:
    insights = []
    if not p.get('rajju'):
        insights.append(
            'Rajju dosham: long-term stability of the relationship may need careful astrological review'
        )
    if not p.get('gana'):
        insights.append('Ganam mismatch: daily temperament and emotional pace may not feel natural to both')
    if not p.get('yoni'):
        insights.append('Yoni porutham weak: instinctive rapport and comfort may take more conscious work')
    minor_fail = sum(
        1 for k in ('dina', 'mahendra', 'sthree_deergha', 'vedha', 'vasya') if not p.get(k)
    )
    if minor_fail >= 3 and p.get('rajju'):
        insights.append('Several secondary poruthams are weak; overall harmony may vary')
    if not p.get('rajju') or float(score) <= 3:
        insights.append('Astrological consultation is recommended')
    if not insights:
        insights.append('No major traditional alerts beyond the porutham checklist')
    return insights


def generate_ui_config() -> dict:
    return {
        'version': 1,
        'summary_score_grades': [
            {'min_score': 0, 'max_score': 3, 'grade': 'Poor', 'color_code': 'red'},
            {'min_score': 4, 'max_score': 6, 'grade': 'Average', 'color_code': 'orange'},
            {'min_score': 7, 'max_score': 10, 'grade': 'Good', 'color_code': 'green'},
        ],
        'porutham_severity_map': {
            'high': ['rajju'],
            'medium': ['gana', 'yoni'],
            'low': [
                'dina',
                'mahendra',
                'sthree_deergha',
                'rasi',
                'rasi_adhipathi',
                'vasya',
                'vedha',
            ],
        },
        'analysis_category_keys': {
            'critical': ['rajju'],
            'moderate': ['gana', 'yoni'],
            'minor': ['dina', 'mahendra', 'sthree_deergha', 'vedha', 'vasya'],
        },
    }
