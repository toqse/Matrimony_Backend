"""

Thalakkuri Calculator

All astronomical data from DOB/TOB/lat/lon using pyswisseph.



IMPORTANT:

- NEVER check is_calculated.

- A horoscope is "ready" when pr_rasi has 11 characters.

- Chart data comes from pr_rasi, pr_amsa, pr_bhav.

- Astronomical data is calculated from pr_dob, pr_tob, pr_lat, pr_lon, pr_tz.

"""

from __future__ import annotations



import os

from datetime import date as dt_date, timedelta



import swisseph as swe



EPHE_PATH = '/usr/share/ephe'



# ── Malayalam lookup tables ──────────────────────────────

RASI_ML = ['മേടം', 'ഇടവം', 'മിഥുനം', 'കർക്കടകം', 'ചിങ്ങം', 'കന്നി',

           'തുലാം', 'വൃശ്ചികം', 'ധനു', 'മകരം', 'കുംഭം', 'മീനം']



NAK_ML = [

    'അശ്വതി', 'ഭരണി', 'കാർത്തിക', 'രോഹിണി', 'മകയിരം', 'തിരുവാതിര',

    'പുണർതം', 'പൂയം', 'ആയില്യം', 'മകം', 'പൂരം', 'ഉത്രം', 'അത്തം',

    'ചിത്ര', 'ചോതി', 'വിശാഖം', 'അനിഴം', 'തൃക്കേട്ട', 'മൂലം',

    'പൂരാടം', 'ഉത്രാടം', 'തിരുവോണം', 'അവിട്ടം', 'ചതയം',

    'പൂരുരുട്ടാതി', 'ഉത്തൃട്ടാതി', 'രേവതി',

]



NAK_LORD_ML = [

    'ശിവി', 'ശുക്രൻ', 'രവി', 'ചന്ദ്രൻ', 'ചൊവ്വ', 'രാഹു', 'ഗുരു', 'ശനി', 'ബുധൻ',

] * 3



TITHI_ML = [

    'പ്രഥമ', 'ദ്വിതീയ', 'തൃതീയ', 'ചതുർഥി', 'പഞ്ചമി', 'ഷഷ്ഠി', 'സപ്തമി',

    'അഷ്ടമി', 'നവമി', 'ദശമി', 'ഏകാദശി', 'ദ്വാദശി', 'ത്രയോദശി', 'ചതുർദ്ദശി', 'അമാവാസി',

    'പ്രഥമ', 'ദ്വിതീയ', 'തൃതീയ', 'ചതുർഥി', 'പഞ്ചമി', 'ഷഷ്ഠി', 'സപ്തമി',

    'അഷ്ടമി', 'നവമി', 'ദശമി', 'ഏകാദശി', 'ദ്വാദശി', 'ത്രയോദശി', 'ചതുർദ്ദശി', 'പൗർണ്ണമി',

]

PAKSHA_ML = ['ശുക്ലപക്ഷ', 'കൃഷ്ണപക്ഷ']



# Jyothishadeepti yoga names (27 nitya yogas)

YOGA_ML = [

    'വിഷ്കംഭ', 'പ്രീതി', 'ആയുഷ്മാൻ', 'സൗഭാഗ്യ', 'ശോഭന', 'അതിഗണ്ഡ', 'സുകർമ',

    'ധൃതി', 'ശൂല', 'ഗണ്ഡ', 'വൃദ്ധി', 'ധ്രുവ', 'വ്യാഘാത', 'ഹർഷണ', 'വജ്ര',

    'സിദ്ധി', 'വ്യതീപാത', 'വരീയൻ', 'പരിഘ', 'ശിവ', 'സിദ്ധ', 'സാദ്ധ്യ',

    'ശുഭ', 'ശുക്ല', 'ബ്രാഹ്മനാമ', 'ഇന്ദ്ര', 'വൈധൃതി',

]



# Jyothishadeepti karana names (11 karanas)

KARANA_ML = [

    'ബവ', 'ബാലവ', 'കൗലവ', 'തൈതില', 'ഗര', 'വണിജ', 'വിഷ്ടി',

    'ശകുനി', 'ചതുഷ്പദ', 'കഴുത', 'കിംസ്തുഘ്ന',

]



WEEKDAY_ML = ['ഞായർ', 'തിങ്കൾ', 'ചൊവ്വ', 'ബുധൻ', 'വ്യാഴം', 'വെള്ളി', 'ശനി']



# Kollavarsham months (Chingam = index 0)

MAL_MONTHS_ML = [

    'ചിങ്ങം', 'കന്നി', 'തുലാം', 'വൃശ്ചികം', 'ധനു', 'മകരം',

    'കുംഭം', 'മീനം', 'മേടം', 'ഇടവം', 'മിഥുനം', 'കർക്കടകം',

]



# Season (ritu) by Kollavarsham month index (Chingam=0 … Karkidakam=11)

SEASON_BY_KOLLAM_MONTH = [

    'വർഷ', 'വർഷ', 'ശരത്', 'ശരത്', 'ഹേമന്ത', 'ഹേമന്ത',

    'ശിശിര', 'ശിശിര', 'വസന്ത', 'വസന്ത', 'ഗ്രീഷ്മ', 'ഗ്രീഷ്മ',

]



# Indian National (Saka) solar month names

SAKA_MONTHS_ML = [

    'ചൈത്രം', 'വൈശാഖം', 'ജ്യേഷ്ഠം', 'ആഷാഢം', 'ശ്രാവണം', 'ഭാദ്രപദം',

    'ആശ്വയുജം', 'കാർത്തികം', 'മാർഗശീർഷം', 'പൗഷം', 'മാഘം', 'ഫാൽഗുണം',

]

# INC month lengths (Chaitra/Vaisakha vary slightly; standard table)

SAKA_MONTH_DAYS = [30, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 30]



GREG_MONTHS_ML = [

    '', 'ജനുവരി', 'ഫെബ്രുവരി', 'മാർച്ച്', 'ഏപ്രിൽ', 'മേയ്', 'ജൂൺ',

    'ജൂലൈ', 'ഓഗസ്റ്റ്', 'സെപ്റ്റംബർ', 'ഒക്ടോബർ', 'നവംബർ', 'ഡിസംബർ',

]



PADA_ORDINAL_ML = ['', 'ഒന്നാം', 'ദ്വിതീയ', 'തൃതീയ', 'ചതുർഥ']

DATE_ORDINAL_ML = ['', 'ഒന്നാം', 'രണ്ടാം', 'മൂന്നാം', 'നാലാം', 'ഐഞ്ചാം',

                   'ആറാം', 'ഏഴാം', 'എട്ടാം', 'ഒമ്പതാം', 'പത്താം']

DREKKANA_ORDINAL_ML = ['', 'പ്രഥമ', 'ദ്വിതീയ', 'തൃതീയ']

GANA_ML = {
    'Deva': 'ദേവ',
    'Manusha': 'മനുഷ്യ',
    'Manushya': 'മനുഷ്യ',
    'Asura': 'രാക്ഷസ',
}



PLANET_RASI_SUFFIX = {

    'Ravi': 'ശുനി',

    'Chandran': 'ചന്ദ്ര',

    'Kuja': 'കുജ',

    'Budhan': 'ബുധ',

    'Guru': 'ഗുരു',

    'Sukran': 'ശുക്ര',

    'Sani': 'ശനി',

}



DASA_LORD_ML = [

    '', 'ശിവി', 'ശുക്രൻ', 'രവി', 'ചന്ദ്രൻ', 'ചൊവ്വ', 'രാഹു',

    'ഗുരു', 'ശനി', 'ബുധൻ', 'ശിവി', 'ശുക്രൻ', 'രവി', 'ചന്ദ്രൻ',

    'ചൊവ്വ', 'രാഹു', 'ഗുരു', 'ശനി', 'ബുധൻ', 'ശിവി', 'ശുക്രൻ',

    'രവി', 'ചന്ദ്രൻ', 'ചൊവ്വ', 'രാഹു', 'ഗുരു', 'ശനി', 'ബുധൻ',

]



_THALAKKURI_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'fonts')
_WIN_FONTS = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')

MALAYALAM_FONT_CANDIDATES = [
    os.path.join(_THALAKKURI_FONT_DIR, 'Rachana-Regular.ttf'),
    '/usr/share/fonts/truetype/malayalam/Rachana-Regular.ttf',
    '/usr/share/fonts/truetype/SMC/Rachana-Regular.ttf',
    os.path.join(_WIN_FONTS, 'Rachana-Regular.ttf'),
    os.path.join(_WIN_FONTS, 'ML-TTKarthika Normal.ttf'),
    '/usr/share/fonts/truetype/noto/NotoSerifMalayalam-Regular.ttf',
    '/usr/share/fonts/truetype/noto/NotoSansMalayalam-Regular.ttf',
    '/usr/share/fonts/truetype/noto/NotoSansMalayalam.ttf',
    os.path.join(_WIN_FONTS, 'NotoSansMalayalam-Regular.ttf'),
    '/usr/share/fonts/opentype/noto/NotoSansMalayalam-Regular.ttf',
    '/usr/share/fonts/truetype/noto-core/NotoSansMalayalam-Regular.ttf',
]

THALAKKURI_FONT_FAMILY = 'ML Karthika'



# ── Chart helpers (same as jathagam.py) ─────────────────

LETTER_TO_SIGN = {c: i + 1 for i, c in enumerate('ABCDEFGHIJKL')}

PLANET_ML_MAP = {

    'la': 'ല', 'su': 'ര', 'mo': 'ച', 'ma': 'കു', 'me': 'ബു',

    'ju': 'ഗു', 've': 'ശു', 'sa': 'മ', 'ra': 'സ', 'ke': 'ശി', 'md': 'മാ',

}

PLANETS_ORDER = ['la', 'su', 'mo', 'ma', 'me', 'ju', 've', 'sa', 'ra', 'ke', 'md']

CHART_LAYOUT = [

    [12, 1, 2, 3],

    [11, None, None, 4],

    [10, None, None, 5],

    [9, 8, 7, 6],

]





def _malayalam_font_path() -> str | None:

    for path in MALAYALAM_FONT_CANDIDATES:

        if os.path.isfile(path):

            return path

    return None


def _format_coord_dms(value: float) -> str:
    """Degrees:minutes for lat/lon display (Jyothishadeepti style)."""
    abs_val = abs(float(value))
    degrees = int(abs_val)
    minutes = int(round((abs_val - degrees) * 60))
    if minutes == 60:
        degrees += 1
        minutes = 0
    return f'{degrees}:{minutes:02d}'


def _thalakkuri_assets_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..',
        'templates',
        'astrology',
        'assets',
    )





def _date_ordinal_ml(day: int) -> str:

    if 1 <= day <= len(DATE_ORDINAL_ML) - 1:

        return DATE_ORDINAL_ML[day]

    return f'{day}-ാം'





def _pada_ordinal_ml(pada) -> str:

    try:

        p = int(pada)

    except (TypeError, ValueError):

        return str(pada or '')

    if 1 <= p <= 4:

        return PADA_ORDINAL_ML[p]

    return f'{p}-ാം'





def _drekkana_phrase(deg_in_rasi: float) -> str:

    idx = min(3, max(1, int(deg_in_rasi / 10) + 1))

    return f'{DREKKANA_ORDINAL_ML[idx]}ദ്രേക്കാണത്തിൽ'





def _planet_rasi_phrase(rasi_ml: str, planet_en: str) -> str:

    suffix = PLANET_RASI_SUFFIX.get(planet_en, '')

    if not rasi_ml or not suffix:

        return ''

    return f'{rasi_ml}{suffix}'





def _format_tob_ml(tob) -> str:

    if not tob:

        return '—'

    if hasattr(tob, 'hour'):

        h, m = tob.hour, tob.minute

    else:

        parts = str(tob).split(':')

        h = int(parts[0])

        m = int(parts[1]) if len(parts) > 1 else 0

    if h < 12:

        period = 'പകൽ'

        h12 = h if h else 12

    elif h == 12:

        period = 'പകൽ'

        h12 = 12

    else:

        period = 'രാത്രി'

        h12 = h - 12

    if m:

        return f'{period} {h12}മ {m}മി'

    return f'{period} {h12}മ'





def _format_dasa_ml(days) -> str:

    from .charts import format_dasa_balance



    if not days or days <= 0:

        return '0വ 0മാ 0ദിവസ'

    b = format_dasa_balance(days)

    return f"{b['years']}വ {b['months']}മാ {b['days']}ദിവസ"





def _get_dasa_display_legacy(days):

    """Legacy format kept for chart centre panel."""

    from .charts import format_dasa_balance



    if not days or days <= 0:

        return '00 വർഷം 00 മാസം 00 ദിവസം'

    b = format_dasa_balance(days)

    return (

        f"{b['years']:02d} വർഷം {b['months']:02d} മാസം {b['days']:02d} ദിവസം"

    )





def _gana_ml(gana: str, star_num: int) -> str:

    if gana:

        return GANA_ML.get(gana, gana)

    from .management.commands.mark_horoscope_done import get_gana

    return GANA_ML.get(get_gana(star_num), 'മനുഷ്യ')





def _gender_ml(gender: str | None) -> str:

    if gender == 'F':

        return 'സ്ത്രീജനം'

    if gender == 'M':

        return 'പുരുഷജനം'

    return 'ജനനം'





def _saka_chaitra1(greg_year: int) -> dt_date:

    """Indian National Calendar: Chaitra 1 falls on March 21/22."""

    if greg_year % 4 == 0 and (greg_year % 100 != 0 or greg_year % 400 == 0):

        return dt_date(greg_year, 3, 21)

    return dt_date(greg_year, 3, 22)





def _saka_date(dob: dt_date) -> tuple[int, str, int]:

    """Gregorian → (Saka year, Malayalam month name, day)."""

    chaitra1 = _saka_chaitra1(dob.year)

    saka_year = dob.year - 78

    if dob < chaitra1:

        saka_year -= 1

        chaitra1 = _saka_chaitra1(dob.year - 1)



    delta = (dob - chaitra1).days + 1

    month_idx = 0

    while month_idx < 12:

        month_len = SAKA_MONTH_DAYS[month_idx]

        if delta <= month_len:

            return saka_year, SAKA_MONTHS_ML[month_idx], delta

        delta -= month_len

        month_idx += 1

    return saka_year, SAKA_MONTHS_ML[11], delta





def _sun_sid_lon(jd: float, ayan: float) -> float:

    pos, _ = swe.calc_ut(jd, swe.SUN)

    return (pos[0] - ayan) % 360





def _find_sankranti_jd(jd: float, ayan: float, target_rasi: int) -> float:

    """JD when Sun most recently entered sidereal rasi (0-11) before jd."""

    target = target_rasi * 30.0

    lo = jd - 35.0

    hi = jd

    for _ in range(60):

        mid = (lo + hi) / 2.0

        lon = _sun_sid_lon(mid, ayan)

        rasi = int(lon / 30) % 12

        if rasi == target_rasi:

            hi = mid

        else:

            lo = mid

    return hi





def _kollavarsham_date(dob: dt_date, jd: float, ayan: float) -> tuple[int, str, int]:

    """Gregorian → (Kollam year, Malayalam month, day in month)."""

    sun_lon = _sun_sid_lon(jd, ayan)

    sun_rasi = int(sun_lon / 30) % 12

    kollam_month_idx = (sun_rasi - 4) % 12

    kollam_month = MAL_MONTHS_ML[kollam_month_idx]



    kollam_year = dob.year - 824

    if dob < dt_date(dob.year, 8, 17):

        kollam_year -= 1



    sankranti_jd = _find_sankranti_jd(jd, ayan, sun_rasi)

    y, m, d, _ = swe.revjul(sankranti_jd, swe.GREG_CAL)

    sankranti_date = dt_date(int(y), int(m), int(d))

    kollam_day = (dob - sankranti_date).days + 1

    if kollam_day < 1:

        kollam_day = int(sun_lon % 30) + 1

    return kollam_year, kollam_month, kollam_day





def decode_chart(chart_str):

    houses = {i: [] for i in range(1, 13)}

    lagna_sign = None

    if not chart_str or len(chart_str) < 11:

        return houses, None

    for idx, key in enumerate(PLANETS_ORDER):

        sign = LETTER_TO_SIGN.get(chart_str[idx].upper())

        if sign:

            houses[sign].append(PLANET_ML_MAP[key])

            if key == 'la':

                lagna_sign = sign

    return houses, lagna_sign





def build_chart_rows(chart_str):

    houses, lagna_sign = decode_chart(chart_str)

    rows = []

    for row in CHART_LAYOUT:

        cells = []

        for num in row:

            if num is None:

                cells.append({'type': 'center'})

            else:

                cells.append({

                    'type': 'house',

                    'num': num,

                    'rasi': RASI_ML[num - 1],

                    'planets': ' '.join(houses.get(num, [])),

                    'is_lagna': num == lagna_sign,

                })

        rows.append(cells)

    return rows





# ── Astronomy helpers ────────────────────────────────────

def _get_jd(dob, tob, tz=5.5):

    if hasattr(tob, 'total_seconds'):

        total = tob.total_seconds()

        h = int(total // 3600)

        m = int((total % 3600) // 60)

        s = 0

    else:

        parts = str(tob).split(':')

        h = int(parts[0])

        m = int(parts[1])

        s = int(parts[2]) if len(parts) > 2 else 0

    ut = h + m / 60.0 + s / 3600.0 - tz

    day = dob.day

    if ut < 0:

        ut += 24

        day -= 1

    elif ut >= 24:

        ut -= 24

        day += 1

    return swe.julday(dob.year, dob.month, day, ut)





def _lon_to_rasi_dms(lon):

    lon = lon % 360

    rasi = int(lon / 30)

    rem = lon - rasi * 30

    d = int(rem)

    m = int((rem - d) * 60)

    s = int(((rem - d) * 60 - m) * 60)

    return rasi, d, m, s





def _nak_pada(lon):

    nak = int(lon / (360 / 27)) % 27

    pada = int((lon % (360 / 27)) / (360 / 27 / 4)) + 1

    return nak, pada





def _jd_to_local_time(jd, tz=5.5):

    """Returns time as: 6മ 7മി 55സെക്കൻഡ്"""

    frac = ((jd + 0.5) % 1) * 24 + tz

    if frac >= 24:

        frac -= 24

    h = int(frac)

    m = int((frac - h) * 60)

    s = int(((frac - h) * 60 - m) * 60)

    return f'{h}മ {m}മി {s}സെക്കൻഡ്'





def _ml_rasi_from_chart(chart_str, planet_index):

    """Malayalam rasi name at 1-indexed planet position in pr_rasi string."""

    if not chart_str or len(chart_str) < planet_index:

        return ''

    sign = LETTER_TO_SIGN.get(chart_str[planet_index - 1].upper())

    if not sign or not (1 <= sign <= 12):

        return ''

    return RASI_ML[sign - 1]





def _format_tob_ampm(tob):

    """12-hour clock with AM/PM for chart centre panel (matches admin UI)."""

    if not tob:

        return ''

    if hasattr(tob, 'hour'):

        h, m = tob.hour, tob.minute

    else:

        parts = str(tob).split(':')

        h = int(parts[0])

        m = int(parts[1]) if len(parts) > 1 else 0

    ampm = 'AM' if h < 12 else 'PM'

    h12 = h % 12 or 12

    return f'{h12:02d}:{m:02d} {ampm}'





def _build_rasi_center(hp, star_ml, star_pada, dasa_lord, dasa_disp):

    """Centre panel for Rasi chart — same fields as admin SouthIndianChart."""

    pada = star_pada if star_pada not in (None, '', '—') else None

    star_line = star_ml or ''

    if star_line and pada:

        star_line = f'{star_line} - പാദം {pada}'



    lagnam_ml = _ml_rasi_from_chart(hp.pr_rasi, 1)

    moon_rasi_ml = _ml_rasi_from_chart(hp.pr_rasi, 3)

    lagna_rasi_parts = []

    if lagnam_ml:

        lagna_rasi_parts.append(f'ലഗ്നം: {lagnam_ml}')

    if moon_rasi_ml:

        lagna_rasi_parts.append(f'രാശി: {moon_rasi_ml}')

    lagna_rasi_line = ' - '.join(lagna_rasi_parts)



    dob_str = hp.pr_dob.strftime('%d-%m-%Y') if hp.pr_dob else ''



    return {

        'name': (hp.pr_name or '').strip(),

        'dob': dob_str,

        'tob': _format_tob_ampm(hp.pr_tob),

        'star_line': star_line,

        'dasa_lord': dasa_lord or '',

        'dasa_disp': dasa_disp or '',

        'lagna_rasi_line': lagna_rasi_line,

    }





# ── Main calculator ──────────────────────────────────────

def calculate_all(hp, gender=None):

    swe.set_ephe_path(EPHE_PATH)

    swe.set_sid_mode(swe.SIDM_LAHIRI)



    lat = float(hp.pr_lat or 0.0)

    lon = float(hp.pr_lon or 0.0)

    tz = float(hp.pr_tz or 5.5)

    dob = hp.pr_dob

    tob = hp.pr_tob or '00:00:00'

    jd = _get_jd(dob, tob, tz)



    ayan = swe.get_ayanamsa_ut(jd)

    a_d = int(ayan)

    a_m = int((ayan - a_d) * 60)

    a_s = int(((ayan - a_d) * 60 - a_m) * 60)

    ayan_display = f'{a_d:02d}:{a_m:02d}:{a_s:02d}'



    PLANET_IDS = [

        (swe.SUN, 'ര', 'Ravi'),

        (swe.MOON, 'ച', 'Chandran'),

        (swe.MARS, 'കു', 'Kuja'),

        (swe.MERCURY, 'ബു', 'Budhan'),

        (swe.JUPITER, 'ഗു', 'Guru'),

        (swe.VENUS, 'ശു', 'Sukran'),

        (swe.SATURN, 'മ', 'Sani'),

        (swe.TRUE_NODE, 'സ', 'Rahu'),

    ]



    planet_rows = []

    rahu_sid = None



    for pid, ml, en in PLANET_IDS:

        pos, _ = swe.calc_ut(jd, pid, swe.FLG_SWIEPH | swe.FLG_SPEED)

        sid = (pos[0] - ayan) % 360

        speed = pos[3]

        rasi, d, m, s = _lon_to_rasi_dms(sid)

        nak, pada = _nak_pada(sid)

        gati = 'വ' if speed < 0 else 'ക്ര'

        if en == 'Rahu':

            rahu_sid = sid

        planet_rows.append({

            'ml': ml, 'en': en,

            'rasi_ml': RASI_ML[rasi],

            'sphuta': f'{d:02d}:{m:02d}:{s:02d}',

            'nak_ml': NAK_ML[nak], 'nak_pada': pada,

            'nak_lord': NAK_LORD_ML[nak],

            'gati': gati,

            'bhava': 0,

        })



    k_sid = (rahu_sid + 180) % 360

    rasi, d, m, s = _lon_to_rasi_dms(k_sid)

    nak, pada = _nak_pada(k_sid)

    planet_rows.append({

        'ml': 'ശി', 'en': 'Kethu',

        'rasi_ml': RASI_ML[rasi],

        'sphuta': f'{d:02d}:{m:02d}:{s:02d}',

        'nak_ml': NAK_ML[nak], 'nak_pada': pada,

        'nak_lord': NAK_LORD_ML[nak],

        'gati': 'വ', 'bhava': 0,

    })



    cusps, ascmc = swe.houses(jd, lat, lon, b'P')

    asc_sid = (ascmc[0] - ayan) % 360

    rasi, d, m, s = _lon_to_rasi_dms(asc_sid)

    nak, pada = _nak_pada(asc_sid)

    lagnam_row = {

        'ml': 'ല', 'en': 'Lagnam',

        'rasi_ml': RASI_ML[rasi],

        'sphuta': f'{d:02d}:{m:02d}:{s:02d}',

        'nak_ml': NAK_ML[nak], 'nak_pada': pada,

        'nak_lord': NAK_LORD_ML[nak],

        'gati': '...', 'bhava': 1,

    }



    weekday = int(jd + 1.5) % 7

    gh_start = [26, 22, 18, 14, 10, 6, 2][weekday]

    dinantham_s = '—'

    try:

        geopos = (lon, lat, 0)

        sr_jd = swe.rise_trans(jd - 0.5, swe.SUN, swe.CALC_RISE, geopos,

                               1013.25, 10)[1][0]

        ss_jd = swe.rise_trans(jd - 0.5, swe.SUN, swe.CALC_SET, geopos,

                               1013.25, 10)[1][0]

        day_len = ss_jd - sr_jd

        maan_jd = sr_jd + gh_start * (day_len / 30.0)

        mpos, _ = swe.calc_ut(maan_jd, swe.SATURN)

        m_sid = (mpos[0] - ayan) % 360

        sunrise_s = _jd_to_local_time(sr_jd, tz)

        sunset_s = _jd_to_local_time(ss_jd, tz)

        try:

            next_sr_jd = swe.rise_trans(ss_jd, swe.SUN, swe.CALC_RISE, geopos,

                                        1013.25, 10)[1][0]

            dinantham_s = _jd_to_local_time(next_sr_jd, tz)

        except Exception:

            dinantham_s = sunrise_s

    except Exception:

        m_sid = 0

        sunrise_s = '—'

        sunset_s = '—'



    rasi, d, m, s = _lon_to_rasi_dms(m_sid)

    nak, pada = _nak_pada(m_sid)

    maandi_row = {

        'ml': 'മാ', 'en': 'Maandi',

        'rasi_ml': RASI_ML[rasi],

        'sphuta': f'{d:02d}:{m:02d}:{s:02d}',

        'nak_ml': NAK_ML[nak], 'nak_pada': pada,

        'nak_lord': NAK_LORD_ML[nak],

        'gati': '...', 'bhava': 0,

    }



    cusp_values = list(cusps[1:13]) if len(cusps) >= 13 else list(cusps[:12])

    sid_cusps = [(c - ayan) % 360 for c in cusp_values]



    def bhava_of(sid_lon):

        if len(sid_cusps) < 12:

            return '—'

        for i in range(12):

            j = (i + 1) % 12

            a = sid_cusps[i]

            b = sid_cusps[j]

            if a <= b:

                if a <= sid_lon < b:

                    return i + 1

            else:

                if sid_lon >= a or sid_lon < b:

                    return i + 1

        return '—'



    for p in planet_rows:

        try:

            r_idx = RASI_ML.index(p['rasi_ml'])

            d_val, m_val, s_val = [int(x) for x in p['sphuta'].split(':')]

            sid = r_idx * 30 + d_val + m_val / 60 + s_val / 3600

            p['bhava'] = bhava_of(sid)

        except Exception:

            p['bhava'] = '—'



    maandi_row['bhava'] = bhava_of(m_sid)

    full_planet_table = [lagnam_row] + planet_rows + [maandi_row]



    sp_sun, _ = swe.calc_ut(jd, swe.SUN)

    sp_moon, _ = swe.calc_ut(jd, swe.MOON)

    sun_s = (sp_sun[0] - ayan) % 360

    moon_s = (sp_moon[0] - ayan) % 360

    diff = (moon_s - sun_s) % 360



    tithi_num = int(diff / 12)

    paksha = 0 if tithi_num < 15 else 1

    tithi_display = f'{PAKSHA_ML[paksha]} {TITHI_ML[tithi_num]}'



    yoga_idx = int(((sun_s + moon_s) % 360) / (360 / 27)) % 27

    karana_i = int(diff / 6) % 11



    wd_ml = WEEKDAY_ML[weekday]

    sun_rasi = int(sun_s / 30)

    ayanam = 'ഉത്തരായനകാലം' if sun_rasi in [9, 10, 11, 0, 1, 2] else 'ദക്ഷിണായനകാലം'



    kollam_year, kollam_month, kollam_day = _kollavarsham_date(dob, jd, ayan)

    kollam_month_idx = MAL_MONTHS_ML.index(kollam_month)

    season = SEASON_BY_KOLLAM_MONTH[kollam_month_idx]



    saka_year, saka_month, saka_day = _saka_date(dob)



    kali_epoch = swe.julday(-3101, 1, 23, 0)

    kali_day = int(swe.julday(dob.year, dob.month, dob.day, 0) - kali_epoch)



    star_num = hp.pr_star or 0

    star_ml = NAK_ML[star_num - 1] if 1 <= star_num <= 27 else '—'

    star_pada = hp.pr_pada or '—'

    star_pada_ml = _pada_ordinal_ml(star_pada)

    dasa_lord = DASA_LORD_ML[star_num] if 1 <= star_num <= 27 else '—'

    dasa_disp = _get_dasa_display_legacy(hp.pr_dasabalance)

    dasa_display_ml = _format_dasa_ml(hp.pr_dasabalance)



    tob_display = str(hp.pr_tob)[:5] if hp.pr_tob else '—'

    tob_ml = _format_tob_ml(hp.pr_tob)



    lagnam_rasi_ml = lagnam_row['rasi_ml']

    moon_rasi_ml = planet_rows[1]['rasi_ml']

    lagna_deg = asc_sid % 30

    lagna_degree_ml = _drekkana_phrase(lagna_deg)



    sun_row = planet_rows[0]

    guru_row = planet_rows[4]

    sun_rasi_phrase = _planet_rasi_phrase(sun_row['rasi_ml'], 'Ravi')

    guru_rasi_phrase = _planet_rasi_phrase(guru_row['rasi_ml'], 'Guru')



    gana_ml = _gana_ml(getattr(hp, 'gana', ''), star_num)

    gender_ml = _gender_ml(gender)

    greg_month_ml = GREG_MONTHS_ML[dob.month] if dob.month else ''

    greg_day_ordinal = _date_ordinal_ml(dob.day)



    rasi_rows = build_chart_rows(hp.pr_rasi)

    amsa_rows = build_chart_rows(hp.pr_amsa)

    bhav_rows = build_chart_rows(hp.pr_bhav)



    rasi_center = _build_rasi_center(

        hp, star_ml, star_pada, dasa_lord, dasa_disp,

    )



    return {

        'hp': hp,

        'dob_display': dob.strftime('%d-%m-%Y'),

        'tob_display': tob_display,

        'tob_ml': tob_ml,

        'ayanamsa': ayan_display,

        'planet_table': full_planet_table,

        'tithi': tithi_display,

        'yoga': YOGA_ML[yoga_idx],

        'karana': KARANA_ML[karana_i],

        'weekday_ml': wd_ml,

        'ayanam': ayanam,

        'season': season,

        'mal_month': kollam_month,

        'kollam_year': kollam_year,

        'kollam_month': kollam_month,

        'kollam_day': kollam_day,

        'saka_year': saka_year,

        'saka_month': saka_month,

        'saka_day': saka_day,

        'kali_dinam': kali_day,

        'star_ml': star_ml,

        'star_pada': star_pada,

        'star_pada_ml': star_pada_ml,

        'dasa_lord_ml': dasa_lord,

        'dasa_display': dasa_disp,

        'dasa_display_ml': dasa_display_ml,

        'lagnam_rasi_ml': lagnam_rasi_ml,

        'moon_rasi_ml': moon_rasi_ml,

        'lagna_degree_ml': lagna_degree_ml,

        'sun_rasi_phrase': sun_rasi_phrase,

        'guru_rasi_phrase': guru_rasi_phrase,

        'gana_ml': gana_ml,

        'gender_ml': gender_ml,

        'greg_month_ml': greg_month_ml,

        'greg_day_ordinal': greg_day_ordinal,

        'rasi_rows': rasi_rows,

        'amsa_rows': amsa_rows,

        'bhav_rows': bhav_rows,

        'rasi_center': rasi_center,

        'sunrise': sunrise_s,

        'sunset': sunset_s,

        'dinantham': dinantham_s,

        'lat': lat,

        'lon': lon,

        'lat_dms': _format_coord_dms(lat),

        'lon_dms': _format_coord_dms(lon),

    }





def generate_thalakkuri_pdf(hp, gender=None):

    from django.template.loader import render_to_string

    ctx = calculate_all(hp, gender=gender)
    ctx['mal_font_family'] = f'"{THALAKKURI_FONT_FAMILY}", serif'

    html = render_to_string('astrology/thalakkuri.html', ctx)

    try:

        from weasyprint import HTML, CSS

        font_path = _malayalam_font_path()
        font_path = os.path.abspath(font_path) if font_path else None
        font_src = (
            f'url("file:///{font_path.replace(os.sep, "/")}")'
            if font_path else 'local("Rachana")'
        )
        assets_dir = os.path.abspath(_thalakkuri_assets_dir())

        font_css = CSS(string=f'''
            @font-face {{
                font-family: "{THALAKKURI_FONT_FAMILY}";
                src: {font_src};
                font-weight: normal;
                font-style: normal;
            }}
            body {{ font-family: "{THALAKKURI_FONT_FAMILY}", serif; }}
        ''')

        pdf = HTML(
            string=html,
            base_url=f'file:///{assets_dir.replace(os.sep, "/")}/',
        ).write_pdf(stylesheets=[font_css])

        return pdf, 'pdf'

    except Exception as e:

        print(f'weasyprint error: {e}')

        return html.encode('utf-8'), 'html'


