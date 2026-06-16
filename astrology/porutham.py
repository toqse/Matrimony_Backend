"""
Kerala Dashakoot Porutham Engine
Direct Python conversion of VB source code.
DO NOT modify the logic of any function.
"""

from datetime import date, datetime, timedelta

# ── Grade constants ───────────────────────────────────────────
UTHAMAM   = 1
MADHYAMAM = 2
ADHAMAM   = 3
NEECHAM   = 4

# Grade number -> machine-readable name for API/UI (e.g. Madhyamam -> yellow).
GRADE_NAMES = {
    UTHAMAM: 'uthamam',
    MADHYAMAM: 'madhyamam',
    ADHAMAM: 'adhamam',
    NEECHAM: 'neecham',
}

# Canonical 1-27 nakshatra list (1-indexed; STAR_NAMES[0] is unused).
STAR_NAMES = [
    '', 'Ashwini', 'Bharani', 'Karthika', 'Rohini', 'Mrigasira',
    'Thiruvathira', 'Punartham', 'Pooyam', 'Ayilyam', 'Makam',
    'Pooram', 'Uthram', 'Atham', 'Chithra', 'Chothi', 'Vishakam',
    'Anizham', 'Thrikketta', 'Moolam', 'Pooradam', 'Uthradam',
    'Thiruvonam', 'Avittam', 'Chathayam', 'Pooruruttathi',
    'Uthuruttathi', 'Revathi',
]

# Kerala rasi names (1-indexed; RASI_NAMES[0] is unused).
RASI_NAMES = [
    '', 'Medam', 'Edavam', 'Midhunam', 'Kadakam', 'Chingam', 'Kanni',
    'Thulam', 'Vrischikam', 'Dhanu', 'Makaram', 'Kumbham', 'Meenam',
]

# ── Lookup tables (from VB source) ───────────────────────────

# Planet code for each rasi (1=Medam..12=Meenam)
# VB: Adhipan = Oiif(RasiNo, 4,7,5,3,2,5,7,4,6,8,8,6)
ADHIPAN = {
    1: 4,   # Medam   → Mars
    2: 7,   # Edavam  → Venus
    3: 5,   # Midhunam→ Mercury
    4: 3,   # Kadakam → Moon
    5: 2,   # Chingam → Sun
    6: 5,   # Kanni   → Mercury
    7: 7,   # Thulam  → Venus
    8: 4,   # Vrischikam → Mars
    9: 6,   # Dhanu   → Jupiter
    10: 8,  # Makaram → Saturn
    11: 8,  # Kumbham → Saturn
    12: 6,  # Meenam  → Jupiter
}

# sat_mi_sam friends table (from VB sat_mi_sam function)
# Key = planet code, Value = set of compatible planet codes
SAT_MI_SAM_FRIENDS = {
    2: {6},              # Sun     → Jupiter only
    3: {3, 5, 6},        # Moon    → Moon, Mercury, Jupiter
    4: {4, 5, 7},        # Mars    → Mars, Mercury, Venus
    5: {5, 3, 4, 6, 7, 8},  # Mercury → all except Sun
    6: {2, 3, 5, 6, 7, 8},  # Jupiter → all except Mars
    7: {7, 4, 5, 6},     # Venus   → Venus, Mars, Mercury, Jupiter
    8: {8, 5, 6, 7},     # Saturn  → Saturn, Mercury, Jupiter, Venus
}

# Vasya table (from VB Vasyam function)
VASYA = {
    1:  '05&08',
    2:  '04&07',
    3:  '06',
    4:  '09&08',
    5:  '07',
    6:  '03&12',
    7:  '06&10',
    8:  '04',
    9:  '12',
    10: '11&01',
    11: '01',
    12: '10',
}

# Vedha star pairs (from VB Vedha_Dosh function)
# Stars 14-27 have no direct pair (0 means no pair)
VEDHA_STAR = {
    1: 18, 2: 17, 3: 16, 4: 15, 5: 14,
    6: 22, 7: 21, 8: 20, 9: 19, 10: 27,
    11: 26, 12: 25, 13: 24,
}


# ── Helper functions ──────────────────────────────────────────

def inlist(v, *args):
    """VB inlist() — checks if v is in the argument list."""
    return v in args


def mahe_selected(pop_choice, op_num):
    """
    VB MaheSelected() — bitmask check.
    Returns True if bit (op_num-1) is set in pop_choice.
    Used for ganam, yoni, mahendra lookups.
    """
    pow1 = 2 ** (op_num - 1)
    pow2 = 2 * pow1
    p1 = pop_choice % pow1
    p2 = pop_choice % pow2
    return p1 != p2


def ras_dif(a, b):
    """VB ras_dif() — rasi distance from a to b (1-12)."""
    return ((b - a + 12) % 12) + 1


def chart_to_array(chart_str):
    """
    Convert 11-char chart string to 1-indexed integer array.
    arr[0] = 0 (unused)
    arr[1] = Lagnam, arr[2] = Ravi, arr[3] = Chandran (Moon),
    arr[4] = Kuja,   arr[5] = Budhan, arr[6] = Guru,
    arr[7] = Sukran, arr[8] = Sani,   arr[9] = Rahu,
    arr[10] = Kethu, arr[11] = Maandi
    """
    if not chart_str or len(chart_str) < 11:
        return []
    return [0] + [ord(c) - ord('A') + 1 for c in chart_str[:11]]


# ── Star classification functions ─────────────────────────────

def ganam_type(star):
    """
    VB Ganam() — returns 'D' (Deva), 'M' (Manushya), 'A' (Asura).
    Uses bitmask codes from VB source.
    """
    if mahe_selected(69292241, star): return 'D'
    if mahe_selected(51907626, star): return 'M'
    if mahe_selected(13017860, star): return 'A'
    return ''


def yoni_type(star):
    """
    VB yoni_v() — returns 'P' or 'S'.
    Uses bitmask code 20892547 from VB source.
    """
    return 'P' if mahe_selected(20892547, star) else 'S'


# ── 10 Porutham functions ─────────────────────────────────────

def dinam(s_star, s_pada, p_star, p_pada):
    """
    VB dinam() — star + pada distance check.
    s = bride, p = groom.
    """
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
    if inlist(pad_dif, 88, 108):
        por = ADHAMAM
    return por


def sthree_deerga(s_star, p_star):
    """
    VB Stre_Dergham() — star distance >= 15 best, >= 9 medium.
    """
    dif = p_star - s_star + 1 if p_star >= s_star else p_star - s_star + 28
    return UTHAMAM if dif >= 15 else (MADHYAMAM if dif >= 9 else ADHAMAM)


def mahendra(s_star, p_star):
    """
    VB Mahendra_Por() — bitmask check with code 17076808.
    """
    dif = (p_star - s_star + 27) % 27 + 1
    return UTHAMAM if mahe_selected(17076808, dif) else ADHAMAM


def ganam(s_star, p_star):
    """
    VB ganapor() — Deva/Manushya/Asura compatibility.
    Same type = Uthamam. D+M or M+D = Madhyamam. Others = Adhamam.
    """
    sg = ganam_type(s_star)
    pg = ganam_type(p_star)
    if sg == 'D':
        return UTHAMAM if pg == 'D' else (MADHYAMAM if pg == 'M' else ADHAMAM)
    if sg == 'M':
        return UTHAMAM if pg == 'M' else (MADHYAMAM if pg == 'D' else ADHAMAM)
    # sg == 'A'
    return UTHAMAM if pg == 'A' else ADHAMAM


def yoni(s_star, p_star):
    """
    VB YoniPorutham() — P/S type compatibility.
    Bride=S and Groom=P = Uthamam. Bride=S and Groom=S = Madhyamam.
    Bride=P = Adhamam (regardless of groom).
    """
    sy = yoni_type(s_star)
    py = yoni_type(p_star)
    if sy == 'S':
        return UTHAMAM if py == 'P' else MADHYAMAM
    return ADHAMAM


def rasi_porutham(s_star, s_rasi, p_star, p_rasi):
    """
    VB RasiPoruth() — moon sign distance mapping.
    s_rasi and p_rasi are moon rasi codes (1-12).
    Uses EXACT Oiif mapping from VB source:
      dif=1:  same/diff star check
      dif=2:  ADHAMAM
      dif=3:  ADHAMAM
      dif=4:  UTHAMAM
      dif=5:  ADHAMAM
      dif=6:  ADHAMAM
      dif=7:  UTHAMAM
      dif=8:  UTHAMAM if bride rasi is odd else MADHYAMAM
      dif=9:  UTHAMAM
      dif=10: UTHAMAM
      dif=11: UTHAMAM
      dif=12: MADHYAMAM
    """
    dif = ((p_rasi - s_rasi + 12) % 12) + 1
    if dif == 1:
        # Same rasi — depends on whether stars are same or different
        if s_star != p_star:
            return UTHAMAM
        else:
            return ADHAMAM if inlist(
                p_star, 2, 4, 6, 8, 9, 10, 13, 18, 19, 20, 23, 24
            ) else MADHYAMAM
    mapping = {
        2: ADHAMAM,
        3: ADHAMAM,
        4: UTHAMAM,
        5: ADHAMAM,
        6: ADHAMAM,
        7: UTHAMAM,
        8: UTHAMAM if s_rasi % 2 == 1 else MADHYAMAM,
        9:  UTHAMAM,
        10: UTHAMAM,
        11: UTHAMAM,
        12: MADHYAMAM,
    }
    return mapping.get(dif, ADHAMAM)


def rasyadhipam(s_rasi, p_rasi):
    """
    VB rasyadhip_por() / sat_mi_sam() — rasi lord friendship check.
    Uses ADHIPAN to get planet code, then SAT_MI_SAM_FRIENDS to check.
    """
    sp = ADHIPAN.get(s_rasi, 0)
    pp = ADHIPAN.get(p_rasi, 0)
    if sp == pp:
        return UTHAMAM
    return UTHAMAM if pp in SAT_MI_SAM_FRIENDS.get(sp, set()) else ADHAMAM


def vasyam(s_rasi, p_rasi):
    """
    VB Vasyam() — mutual attraction between rasis.
    Checks if groom rasi is in bride's vasya list OR bride in groom's.
    """
    ss = str(s_rasi).zfill(2)
    ps = str(p_rasi).zfill(2)
    return UTHAMAM if (
        ps in VASYA.get(s_rasi, '') or
        ss in VASYA.get(p_rasi, '')
    ) else ADHAMAM


def rajju_dosham(s_star, p_star):
    """
    VB RajjuDosham() — same middle rajju band = NEECHAM.
    """
    def rajju(s):
        r = s % 6
        return 1 if r in (0, 1) else (3 if r in (3, 4) else 2)
    return NEECHAM if rajju(s_star) == 2 and rajju(p_star) == 2 else UTHAMAM


def vedha_dosham(s_star, p_star):
    """
    VB Vedha_Dosh() — opposing/blocking star pairs.
    """
    d = UTHAMAM
    vs = VEDHA_STAR.get(s_star, 0)
    vp = VEDHA_STAR.get(p_star, 0)
    if vs == p_star or vp == s_star:
        d = NEECHAM
    for group in [
        (14, 23, 5),
        (4, 6, 13, 22, 15, 24),
        (3, 7, 12, 16, 21, 25),
    ]:
        if s_star in group and p_star in group:
            d = NEECHAM
    return d


# ── Chovva (Kuja/Mars) Dosham ─────────────────────────────────

def det_chovva(a):
    """
    VB det_chovva() — detailed check, returns True if dosham cannot be eliminated.
    a is 1-indexed array: a[1]=Lagnam..a[11]=Maandi.
    Rules that CANCEL dosham:
      1. Lagnam=Kanni, Mars=Dhanu, Jupiter=Makaram
      2. Jupiter and Venus both in Lagnam
      3. Saturn in Lagnam/7th/4th/9th/12th from Lagnam
      4. Mars with Saturn/Rahu/Kethu/Moon
    """
    # Rule 1: Kanni lagnam + Mars in Dhanu + Jupiter in Makaram
    if a[1] == 6 and a[4] == 9 and a[6] == 10:
        return False
    # Rule 2: Guru and Sukran in Lagnam
    if a[1] == a[6] and a[1] == a[7]:
        return False
    # Rule 3: Sani in 1st/7th/4th/9th/12th from Lagnam
    if inlist(ras_dif(a[1], a[8]), 1, 7, 4, 9, 12):
        return False
    # Rule 4: Mars conjunct Saturn/Rahu/Kethu/Moon
    if inlist(a[4], a[8], a[9], a[10], a[3]):
        return False
    return True


def bride_chovva(a):
    """
    VB bride_chovva() — checks chovva dosham for bride.
    Checks Mars in 7th or 8th from Lagnam with specific lagnam conditions.
    """
    kujpos = ras_dif(a[1], a[4])
    if 7 <= kujpos <= 8 and inlist(a[1], 3, 4, 6, 8, 9, 12):
        cond1 = inlist(a[1], 3, 6, 9, 12) and ras_dif(a[1], a[4]) == 7
        cond2 = inlist(a[1], 4, 8) and ras_dif(a[1], a[4]) == 8
        if cond1 or cond2:
            return True
    return False


def groom_chovva(a):
    """
    VB groom_chovva() — checks chovva dosham for groom.
    Only checks Mars in 7th from Lagnam (not 8th like bride).
    Then calls det_chovva for detailed check.
    """
    kujpos = ras_dif(a[1], a[4])
    if kujpos == 7 and inlist(a[1], 3, 6, 9, 12):
        return det_chovva(a)
    return False


def chovva_dosham(s_chart, p_chart):
    """
    VB chov_dosh() — returns True if bride and groom MATCH in chovva status.
    True = both have dosham OR both don't = compatible.
    False = one has and other doesn't = mismatch (bad).
    """
    sa = chart_to_array(s_chart)
    pa = chart_to_array(p_chart)
    if not sa or not pa:
        return None
    return bride_chovva(sa) == groom_chovva(pa)


# ── Papatha (planetary affliction score) ─────────────────────

def calc_papatha(arr):
    """
    VB CalcPapatha() — weighted malefic points.
    arr is 1-indexed chart array from chart_to_array().
    Plan_No for each iteration:
      i=1: Plan_No=1 (Lagnam)
      i=2: Plan_No=3 (Chandran/Moon)
      i=3: Plan_No=7 (Sukran/Venus)
    papacode positions (1-indexed): 9=Rahu, 2=Ravi, 8=Sani, 4=Kuja
    pos_papatha weights: 12th=1, 2nd=2, 4th=3, 7th=4, 1st=5, 8th=6
    """
    pos_papatha = {12: 1, 2: 2, 4: 3, 7: 4, 1: 5, 8: 6}
    papacode = [0, 9, 2, 8, 4]   # 1-indexed: [1]=Rahu, [2]=Ravi, [3]=Sani, [4]=Kuja
    weit     = [0, 1.0, 0.75, 0.5]  # 1-indexed weights

    tp = 0.0
    for i in range(1, 4):
        plan_no = i * i - i + 1   # i=1→1, i=2→3, i=3→7
        rel = [0] + [
            ((arr[k] - arr[plan_no] + 12) % 12) + 1
            for k in range(1, 12)
        ]
        papatha = sum(
            pos_papatha.get(rel[papacode[j]], 0) * j
            for j in range(1, 5)
        )
        tp += weit[i] * papatha
    return tp


# ── Papasamyam ────────────────────────────────────────────────
# NOTE: The pasted VB source provides CalcPapatha (the per-chart papa score,
# ported above as ``calc_papatha``) but no bride/groom comparison routine, so
# the rule below follows the standard Kerala convention. Swap the body when the
# precise VB logic is supplied.


def papa_samyam(bride_papatha, groom_papatha):
    """
    Papasamyam — balance of malefic (papa) strength between the two charts.
    Returns True (favourable) when the groom's papa is greater than or equal to
    the bride's, i.e. the bride does not carry the heavier affliction.
    Reuses the existing ``calc_papatha`` scores.
    """
    return float(groom_papatha or 0) >= float(bride_papatha or 0)


# ── Dasa Sandhi (VB dsandhipor / dasa_sandhi / dasas) ─────────
# Vimshottari dasha sequence as used by the VB engine: (name, years).
# 1-indexed to mirror VB DasaName(RowId, ...); index 0 is unused.
DASA_TABLE = [
    ('', 0),
    ('BUDHAN', 17),
    ('KETHU', 7),
    ('SUKRAN', 20),
    ('RAVI', 6),
    ('CHANDRAN', 10),
    ('KUJAN', 7),
    ('RAHU', 18),
    ('GURU', 16),
    ('SANI', 19),
]

# VB builds d_array(1..15): row 1 (running dasha) + 14 following dashas.
DASA_ROWS = 15
DASA_DAYS_PER_YEAR = 365.25


def _to_date(value):
    """Coerce a date/datetime to a plain date; return None otherwise."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def build_dasa_end_dates(starcode, sistadura, dob):
    """
    VB ``dasas`` + ``get_dasa1``: list of dasha END dates, 1-indexed (idx 0
    unused). Row 1 = the dasha running at birth, ending at ``dob + sistadura``
    days (the sishta balance). Rows 2..15 = following dashas in Vimshottari
    order, each Int(365.25 * years) long. Returns None if inputs are unusable.
    """
    dob = _to_date(dob)
    if dob is None or starcode is None or sistadura is None:
        return None
    try:
        starcode = int(starcode)
        sistadura = int(sistadura)
    except (TypeError, ValueError):
        return None

    # get_dasa1: dasa_ord = (starcode Mod 9) + 1
    dasacode = (starcode % 9) + 1
    ends = [None] * (DASA_ROWS + 1)
    ends[1] = dob + timedelta(days=sistadura)
    for i in range(2, DASA_ROWS + 1):
        dasacode = (dasacode % 9) + 1
        years = DASA_TABLE[dasacode][1]
        ends[i] = ends[i - 1] + timedelta(days=int(DASA_DAYS_PER_YEAR * years))
    return ends


def _dasa_sandhi_text(s_star, s_dob, s_sista, p_star, p_dob, p_sista, today=None):
    """
    VB ``dasa_sandhi``: returns a non-empty string (the colliding dasha-change
    dates) when bride and groom dasha junctions fall within 365 days of each
    other within the next 70 years; returns '' when there is no sandhi.
    """
    today = _to_date(today) or date.today()
    s_dob = _to_date(s_dob)
    p_dob = _to_date(p_dob)
    s_arr = build_dasa_end_dates(s_star, s_sista, s_dob)
    p_arr = build_dasa_end_dates(p_star, p_sista, p_dob)
    if s_arr is None or p_arr is None:
        return ''

    seventy_years = 70 * DASA_DAYS_PER_YEAR

    # Advance bride counter to the first dasha boundary after today.
    cntr1 = 1
    s_d_date = s_dob
    while s_d_date <= today:
        cntr1 += 1
        if cntr1 > DASA_ROWS:
            return ''
        s_d_date = s_arr[cntr1]

    # Advance groom counter to the first dasha boundary after today.
    cntr2 = 1
    p_d_date = p_dob
    while p_d_date <= today:
        cntr2 += 1
        if cntr2 > DASA_ROWS:
            return ''
        p_d_date = p_arr[cntr2]

    stcntr2 = cntr2

    while (s_d_date - s_dob).days <= seventy_years:
        if cntr1 > DASA_ROWS:
            break
        s_d_date = s_arr[cntr1]
        cntr2 = stcntr2 if cntr2 <= stcntr2 + 2 else cntr2 - 2
        if cntr2 > DASA_ROWS:
            break
        p_d_date = p_arr[cntr2]
        while (
            (p_d_date - p_dob).days < seventy_years
            and (p_d_date - s_d_date).days < 500
        ):
            if cntr2 > DASA_ROWS:
                break
            p_d_date = p_arr[cntr2]
            if abs((s_d_date - p_d_date).days) < 365:
                return f'{s_d_date.isoformat()} {p_d_date.isoformat()}'
            cntr2 += 1
        cntr1 += 1

    return ''


def dasa_sandhi(s_star, s_dob, s_sista, p_star, p_dob, p_sista, today=None):
    """
    VB ``dsandhipor``: ``dasa_sandhi(...) = ""``. Returns True (favourable /
    safe) when there is NO dasa sandhi between the two charts, matching the
    convention used by the other dosham booleans here (True = compatible).
    """
    return _dasa_sandhi_text(
        s_star, s_dob, s_sista, p_star, p_dob, p_sista, today
    ) == ''


# ── Main calculation function ─────────────────────────────────

def calculate_porutham(bride_hp, groom_hp):
    """
    Main entry point. Receives two HoroscopeProfile objects.
    Returns dict with all 10 porutham grades + dosham checks.

    IMPORTANT: s_ prefix = bride, p_ prefix = groom.
    Moon rasi is taken from index [3] of the 1-indexed chart array
    (position 3 = Chandran/Moon in VB 1-indexed array).
    """
    s_star = bride_hp.pr_star or 0
    s_pada = bride_hp.pr_pada or 1
    p_star = groom_hp.pr_star or 0
    p_pada = groom_hp.pr_pada or 1

    s_arr = chart_to_array(bride_hp.pr_rasi)
    p_arr = chart_to_array(groom_hp.pr_rasi)

    # Moon rasi = position 3 in 1-indexed VB array
    s_rasi = s_arr[3] if len(s_arr) >= 4 else 1
    p_rasi = p_arr[3] if len(p_arr) >= 4 else 1

    results = {
        'dinam':         dinam(s_star, s_pada, p_star, p_pada),
        'ganam':         ganam(s_star, p_star),
        'mahendra':      mahendra(s_star, p_star),
        'sthree_deerga': sthree_deerga(s_star, p_star),
        'yoni':          yoni(s_star, p_star),
        'rasi':          rasi_porutham(s_star, s_rasi, p_star, p_rasi),
        'rasyadhipam':   rasyadhipam(s_rasi, p_rasi),
        'vasyam':        vasyam(s_rasi, p_rasi),
        'rajju_dosham':  rajju_dosham(s_star, p_star),
        'vedha_dosham':  vedha_dosham(s_star, p_star),
        'chovva_dosham': chovva_dosham(bride_hp.pr_rasi, groom_hp.pr_rasi),
        'bride_papatha': calc_papatha(s_arr),
        'groom_papatha': calc_papatha(p_arr),
    }

    results['papa_samyam'] = papa_samyam(
        results['bride_papatha'], results['groom_papatha']
    )
    results['dasa_sandhi'] = dasa_sandhi(
        getattr(bride_hp, 'pr_star', None),
        getattr(bride_hp, 'pr_dob', None),
        getattr(bride_hp, 'pr_dasabalance', None),
        getattr(groom_hp, 'pr_star', None),
        getattr(groom_hp, 'pr_dob', None),
        getattr(groom_hp, 'pr_dasabalance', None),
    )

    grade_keys = [
        'dinam', 'ganam', 'mahendra', 'sthree_deerga', 'yoni',
        'rasi', 'rasyadhipam', 'vasyam', 'rajju_dosham', 'vedha_dosham',
    ]

    results['uthamam_count']   = sum(1 for k in grade_keys if results[k] == UTHAMAM)
    results['madhyamam_count'] = sum(1 for k in grade_keys if results[k] == MADHYAMAM)
    results['adhamam_count']   = sum(1 for k in grade_keys if results[k] in (ADHAMAM, NEECHAM))
    results['total_porutham_count'] = results['uthamam_count'] + results['madhyamam_count']

    results['has_dosha'] = (
        any(results[k] == NEECHAM for k in ['rajju_dosham', 'vedha_dosham'])
        or results['chovva_dosham'] is False
        or results['papa_samyam'] is False
        or results['dasa_sandhi'] is False
    )

    # max_score stays at 10 (uthamam_count). Papasamyam / dasa-sandhi do not add
    # to the count but demote the overall grade by one tier each when they fail.
    tiers = ['Not Recommended', 'Average', 'Good', 'Excellent']
    u = results['uthamam_count']
    base_tier = 3 if u >= 8 else 2 if u >= 6 else 1 if u >= 4 else 0
    demotion = (0 if results['papa_samyam'] else 1) + (
        0 if results['dasa_sandhi'] else 1
    )
    results['overall_result'] = tiers[max(0, base_tier - demotion)]

    # Grade strings for API response
    grade_map = {UTHAMAM: 'uthamam', MADHYAMAM: 'madhyamam',
                 ADHAMAM: 'adhamam', NEECHAM: 'neecham'}
    results['grades'] = {k: grade_map.get(results[k], 'adhamam') for k in grade_keys}

    # Boolean pass/fail (Uthamam only = True)
    results['poruthams'] = {k: results[k] == UTHAMAM for k in grade_keys}

    # Ready-to-render dosham/compatibility checks. Each `matched` is a boolean so
    # the UI can show a tick (True) / cross (False) exactly like the porutham
    # rows (Vedha / Rajju / Rasi). True = favourable in every case.
    results['dosha_checks'] = [
        {
            'key': 'chovva_dosham',
            'label': 'Chovva Dosham',
            'matched': results['chovva_dosham'] is True,
        },
        {
            'key': 'papa_samyam',
            'label': 'Papa Samyam',
            'matched': bool(results['papa_samyam']),
        },
        {
            'key': 'dasa_sandhi',
            'label': 'Dasa Sandhi',
            'matched': bool(results['dasa_sandhi']),
        },
    ]

    results['score']     = results['uthamam_count']
    results['max_score'] = 10
    results['result']    = results['overall_result']

    return results
