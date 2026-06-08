# astrology/porutham.py
# Converted from client-provided VB source code.
# All 12 porutham checks for Kerala Dashakoot matching.
# Takes two HoroscopeProfile instances. Returns dict of results.

UTHAMAM = 1
MADHYAMAM = 2
ADHAMAM = 3
NEECHAM = 4

STAR_NAMES = [
    '', 'Ashwini', 'Bharani', 'Karthika', 'Rohini', 'Mrigasira',
    'Thiruvathira', 'Punartham', 'Pooyam', 'Ayilyam', 'Makam',
    'Pooram', 'Uthram', 'Atham', 'Chithra', 'Chothi', 'Vishakam',
    'Anizham', 'Thrikketta', 'Moolam', 'Pooradam', 'Uthradam',
    'Thiruvonam', 'Avittam', 'Chathayam', 'Pooruruttathi',
    'Uthuruttathi', 'Revathi',
]

RASI_NAMES = [
    '', 'Medam', 'Edavam', 'Midhunam', 'Kadakam', 'Chingam', 'Kanni',
    'Thulam', 'Vrischikam', 'Dhanu', 'Makaram', 'Kumbham', 'Meenam',
]


def inlist(val, *args):
    return val in args


def ras_dif(a, b):
    return ((b - a + 12) % 12) + 1


def chart_to_array(s):
    if not s or len(s) < 11:
        return []
    return [ord(c) - ord('A') + 1 for c in s[:11]]


def mahe_selected(pop_choice, op_num):
    pow1 = 2 ** (op_num - 1)
    pow2 = 2 * pow1
    return (pop_choice % pow1) != (pop_choice % pow2)


def dinam(s_star, s_pada, p_star, p_pada):
    dif = ((p_star - s_star + 27) % 27) + 1
    if not inlist(dif, 3, 5, 7, 12, 14, 16, 21, 23, 25):
        por = UTHAMAM
    elif inlist(dif, 7, 16, 25):
        por = MADHYAMAM
    else:
        por = ADHAMAM
    p_pad_code = p_pada + (p_star - 1) * 4
    s_pad_code = s_pada + (s_star - 1) * 4
    pad_dif = ((p_pad_code - s_pad_code + 108) % 108) + 1
    return ADHAMAM if inlist(pad_dif, 88, 108) else por


def sthree_deerga(s_star, p_star):
    dif = p_star - s_star + 1 if p_star >= s_star else p_star - s_star + 28
    return UTHAMAM if dif >= 15 else (MADHYAMAM if dif >= 9 else ADHAMAM)


def mahendra(s_star, p_star):
    dif = (p_star - s_star + 27) % 27 + 1
    return UTHAMAM if mahe_selected(17076808, dif) else ADHAMAM


def ganam_type(n):
    if mahe_selected(69292241, n):
        return 'D'
    if mahe_selected(51907626, n):
        return 'M'
    if mahe_selected(13017860, n):
        return 'A'
    return ''


def ganam(s_star, p_star):
    sg = ganam_type(s_star)
    pg = ganam_type(p_star)
    if sg == 'D':
        return UTHAMAM if pg == 'D' else (MADHYAMAM if pg == 'M' else ADHAMAM)
    if sg == 'M':
        return UTHAMAM if pg == 'M' else (MADHYAMAM if pg == 'D' else ADHAMAM)
    return UTHAMAM if pg == 'A' else ADHAMAM


def yoni_type(n):
    return 'P' if mahe_selected(20892547, n) else 'S'


def yoni(s_star, p_star):
    sy = yoni_type(s_star)
    py = yoni_type(p_star)
    if sy == 'S':
        return UTHAMAM if py == 'P' else MADHYAMAM
    return ADHAMAM


def rasi_porutham(s_star, s_rasi, p_star, p_rasi):
    dif = ((p_rasi - s_rasi + 12) % 12) + 1
    mapping = {
        1: (
            UTHAMAM
            if s_star != p_star
            else ADHAMAM
            if inlist(p_star, 2, 4, 6, 8, 9, 10, 13, 18, 19, 20, 23, 24)
            else MADHYAMAM
        ),
        2: ADHAMAM,
        3: ADHAMAM,
        4: ADHAMAM,
        5: UTHAMAM,
        6: ADHAMAM,
        7: (UTHAMAM if s_rasi % 2 == 1 else MADHYAMAM),
        8: ADHAMAM,
        9: UTHAMAM,
        10: UTHAMAM,
        11: UTHAMAM,
        12: MADHYAMAM,
    }
    return mapping.get(dif, ADHAMAM)


ADHIPAN = {1: 4, 2: 7, 3: 5, 4: 3, 5: 2, 6: 5, 7: 7, 8: 4, 9: 6, 10: 8, 11: 8, 12: 6}
MITHRAM = {
    4: [6],
    7: [3, 5, 6],
    5: [4, 5, 7],
    3: [5, 3, 4, 6, 7, 8],
    2: [2, 3, 5, 6, 7, 8],
    6: [7, 4, 5, 6],
    8: [8, 5, 6, 7],
}


def rasyadhipam(s_rasi, p_rasi):
    sp = ADHIPAN.get(s_rasi, 0)
    pp = ADHIPAN.get(p_rasi, 0)
    return UTHAMAM if pp in MITHRAM.get(sp, []) else ADHAMAM


VASYA = {
    1: '05&08', 2: '04&07', 3: '06', 4: '09&08', 5: '07', 6: '03&12',
    7: '06&10', 8: '04', 9: '12', 10: '11&01', 11: '01', 12: '10',
}


def vasyam(s_rasi, p_rasi):
    ss = str(s_rasi).zfill(2)
    ps = str(p_rasi).zfill(2)
    return UTHAMAM if (ps in VASYA.get(s_rasi, '') or ss in VASYA.get(p_rasi, '')) else ADHAMAM


def rajju(star):
    r = star % 6
    return 1 if r in (0, 1) else (3 if r in (3, 4) else 2)


def rajju_dosham(s_star, p_star):
    return NEECHAM if rajju(s_star) == 2 and rajju(p_star) == 2 else UTHAMAM


VEDHA_STAR = {
    1: 18, 2: 17, 3: 16, 4: 15, 5: 14, 6: 22, 7: 21,
    8: 20, 9: 19, 10: 27, 11: 26, 12: 25, 13: 24,
}


def vedha_dosham(s_star, p_star):
    if VEDHA_STAR.get(s_star) == p_star or VEDHA_STAR.get(p_star) == s_star:
        return NEECHAM
    for grp in [(14, 23, 5), (4, 6, 13, 22, 15, 24), (3, 7, 12, 16, 21, 25)]:
        if s_star in grp and p_star in grp:
            return NEECHAM
    return UTHAMAM


def det_chovva(a):
    if a[0] == 6 and a[3] == 9 and a[5] == 10:
        return False
    if a[0] == a[5] == a[6]:
        return False
    if ras_dif(a[0], a[7]) in (1, 7, 4, 9, 12):
        return False
    if a[3] in (a[7], a[8], a[9], a[2]):
        return False
    return True


def bride_chovva(a):
    kp = ras_dif(a[0], a[3])
    if 7 <= kp <= 8 and a[0] in (3, 4, 6, 8, 9, 12):
        c1 = a[0] in (3, 6, 9, 12) and kp == 7
        c2 = a[0] in (4, 8) and kp == 8
        if c1 or c2:
            return True
    return False


def groom_chovva(a):
    if ras_dif(a[0], a[3]) == 7 and a[0] in (3, 6, 9, 12):
        return det_chovva(a)
    return False


def chovva_dosham(s_chart, p_chart):
    sa = chart_to_array(s_chart)
    pa = chart_to_array(p_chart)
    if not sa or not pa:
        return None
    return bride_chovva(sa) == groom_chovva(pa)


def calc_papatha(aname):
    if len(aname) < 11:
        return 0.0
    pos_papatha = {12: 1, 2: 2, 4: 3, 7: 4, 1: 5, 8: 6}
    papacode = [9, 2, 8, 4]
    weit = [1, 0.75, 0.5]
    plan_nos = [0, 2, 6]
    tpapatha = 0.0
    for i, plan_no in enumerate(plan_nos):
        rel = [((aname[k] - aname[plan_no] + 12) % 12) + 1 for k in range(11)]
        papatha = sum(
            pos_papatha.get(rel[papacode[j] - 1], 0) * (j + 1)
            for j in range(4)
        )
        tpapatha += weit[i] * papatha
    return tpapatha


def calculate_porutham(bride_hp, groom_hp):
    """
    Main function. Takes two HoroscopeProfile instances.
    Returns dict with all 12 porutham results + summary.
    """
    s_star = bride_hp.pr_star or 0
    s_pada = bride_hp.pr_pada or 1
    p_star = groom_hp.pr_star or 0
    p_pada = groom_hp.pr_pada or 1
    s_arr = chart_to_array(bride_hp.pr_rasi)
    p_arr = chart_to_array(groom_hp.pr_rasi)
    s_rasi = s_arr[2] if len(s_arr) >= 3 else 1
    p_rasi = p_arr[2] if len(p_arr) >= 3 else 1

    results = {
        'dinam': dinam(s_star, s_pada, p_star, p_pada),
        'ganam': ganam(s_star, p_star),
        'mahendra': mahendra(s_star, p_star),
        'sthree_deerga': sthree_deerga(s_star, p_star),
        'yoni': yoni(s_star, p_star),
        'rasi': rasi_porutham(s_star, s_rasi, p_star, p_rasi),
        'rasyadhipam': rasyadhipam(s_rasi, p_rasi),
        'vasyam': vasyam(s_rasi, p_rasi),
        'rajju_dosham': rajju_dosham(s_star, p_star),
        'vedha_dosham': vedha_dosham(s_star, p_star),
        'chovva_dosham': chovva_dosham(bride_hp.pr_rasi, groom_hp.pr_rasi),
        'bride_papatha': calc_papatha(s_arr),
        'groom_papatha': calc_papatha(p_arr),
    }

    grade_keys = [
        'dinam', 'ganam', 'mahendra', 'sthree_deerga', 'yoni',
        'rasi', 'rasyadhipam', 'vasyam', 'rajju_dosham', 'vedha_dosham',
    ]
    results['uthamam_count'] = sum(1 for k in grade_keys if results[k] == UTHAMAM)
    results['madhyamam_count'] = sum(1 for k in grade_keys if results[k] == MADHYAMAM)
    results['adhamam_count'] = sum(
        1 for k in grade_keys if results[k] in (ADHAMAM, NEECHAM)
    )
    results['total_porutham_count'] = (
        results['uthamam_count'] + results['madhyamam_count']
    )
    results['has_dosha'] = (
        any(results[k] == NEECHAM for k in ['rajju_dosham', 'vedha_dosham'])
        or results['chovva_dosham'] is False
    )
    u = results['uthamam_count']
    results['overall_result'] = (
        'Excellent' if u >= 8 else
        'Good' if u >= 6 else
        'Average' if u >= 4 else
        'Not Recommended'
    )
    # Backward-compatible fields for existing admin_panel code
    results['poruthams'] = {k: (results[k] == UTHAMAM) for k in grade_keys}
    results['score'] = float(results['uthamam_count'])
    results['max_score'] = 10.0
    results['result'] = results['overall_result']
    return results
