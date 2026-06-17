"""
Thalakkuri Calculator
All astronomical data from DOB/TOB/lat/lon using pyswisseph.

IMPORTANT:
- NEVER check is_calculated.
- A horoscope is "ready" when pr_rasi has 11 characters.
- Chart data comes from pr_rasi, pr_amsa, pr_bhav.
- Astronomical data is calculated from pr_dob, pr_tob, pr_lat, pr_lon, pr_tz.
"""
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

YOGA_ML = [
    'വിഷ്കംഭ', 'പ്രീതി', 'ആയുഷ്മാൻ', 'സൗഭാഗ്യ', 'ശോഭന', 'അതിഗണ്ഡ', 'സുകർമ',
    'ധൃതി', 'ശൂല', 'ഗണ്ഡ', 'വൃദ്ധി', 'ധ്രുവ', 'വ്യാഘാത', 'ഹർഷണ', 'വജ്ര',
    'സിദ്ധി', 'വ്യതീപാത', 'വരീയൻ', 'പരിഘ', 'ശിവ', 'സിദ്ധ', 'സാദ്ധ്യ',
    'ശുഭ', 'ശുക്ല', 'ബ്രഹ്മ', 'ഇന്ദ്ര', 'വൈധൃതി',
]

KARANA_ML = [
    'ബവ', 'ബാലവ', 'കൗലവ', 'തൈതില', 'ഗര', 'വണിജ', 'വിഷ്ടി',
    'ശകുനി', 'ചതുഷ്പദ', 'നാഗ', 'കിംസ്തുഘ്ന',
]

WEEKDAY_ML = ['ഞായർ', 'തിങ്കൾ', 'ചൊവ്വ', 'ബുധൻ', 'വ്യാഴം', 'വെള്ളി', 'ശനി']

MAL_MONTHS_ML = [
    'ചിങ്ങം', 'കന്നി', 'തുലാം', 'വൃശ്ചികം', 'ധനു', 'മകരം',
    'കുംഭം', 'മീനം', 'മേടം', 'ഇടവം', 'മിഥുനം', 'കർക്കടകം',
]

SEASON_ML = [
    'ഗ്രീഷ്മ', 'ഗ്രീഷ്മ', 'വർഷ', 'വർഷ', 'ശരത്', 'ശരത്',
    'ഹേമന്ത', 'ഹേമന്ത', 'ശിശിര', 'ശിശിര', 'വസന്ത', 'വസന്ത',
]

DASA_LORD_ML = [
    '', 'ശിവി', 'ശുക്രൻ', 'രവി', 'ചന്ദ്രൻ', 'ചൊവ്വ', 'രാഹു',
    'ഗുരു', 'ശനി', 'ബുധൻ', 'ശിവി', 'ശുക്രൻ', 'രവി', 'ചന്ദ്രൻ',
    'ചൊവ്വ', 'രാഹു', 'ഗുരു', 'ശനി', 'ബുധൻ', 'ശിവി', 'ശുക്രൻ',
    'രവി', 'ചന്ദ്രൻ', 'ചൊവ്വ', 'രാഹു', 'ഗുരു', 'ശനി', 'ബുധൻ',
]

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


def _get_dasa_display(days):
    """
    Format remaining (shishta) dasa balance in Malayalam style.
    Example: 09 വർഷം 08 മാസം 15 ദിവസം

    Always returns a full zero-padded string. When the balance is
    null/empty/zero, returns "00 വർഷം 00 മാസം 00 ദിവസം".
    """
    from .charts import format_dasa_balance

    if not days or days <= 0:
        return '00 വർഷം 00 മാസം 00 ദിവസം'
    b = format_dasa_balance(days)
    return (
        f"{b['years']:02d} വർഷം {b['months']:02d} മാസം {b['days']:02d} ദിവസം"
    )


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
def calculate_all(hp):
    swe.set_ephe_path(EPHE_PATH)
    swe.set_sid_mode(swe.SIDM_LAHIRI)

    # Coordinates/time may be NULL on legacy records; default rather than 500.
    lat = float(hp.pr_lat or 0.0)
    lon = float(hp.pr_lon or 0.0)
    tz = float(hp.pr_tz or 5.5)
    dob = hp.pr_dob
    tob = hp.pr_tob or '00:00:00'
    jd = _get_jd(dob, tob, tz)

    # Ayanamsa
    ayan = swe.get_ayanamsa_ut(jd)
    a_d = int(ayan)
    a_m = int((ayan - a_d) * 60)
    a_s = int(((ayan - a_d) * 60 - a_m) * 60)
    ayan_display = f'{a_d:02d}:{a_m:02d}:{a_s:02d}'

    # Planet positions
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
            'bhava': 0,  # filled below
        })

    # Kethu = Rahu + 180
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

    # Lagnam
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

    # Maandi (Gulika) — Saturn position at Maandi time
    weekday = int(jd + 1.5) % 7
    gh_start = [26, 22, 18, 14, 10, 6, 2][weekday]
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

    # Bhava numbers (Placidus cusps). pyswisseph can return either a
    # 12-item zero-indexed cusp sequence or a legacy 13-item sequence whose
    # first item is unused; normalize before reading the next cusp.
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

    # Final ordered table: Lagnam first, then planets, then Maandi
    full_planet_table = [lagnam_row] + planet_rows + [maandi_row]

    # Tithi / Yoga / Karana from Sun & Moon sidereal longitudes
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

    # Weekday, season, ayanam
    wd_ml = WEEKDAY_ML[weekday]
    sun_rasi = int(sun_s / 30)
    ayanam = 'ഉത്തരായനകാലം' if sun_rasi in [9, 10, 11, 0, 1, 2] else 'ദക്ഷിണായനകാലം'
    season = SEASON_ML[sun_rasi]
    mal_month = MAL_MONTHS_ML[sun_rasi]

    # Kollam year
    from datetime import date as dt
    kollam = dob.year - 824
    if dt(dob.year, dob.month, dob.day) < dt(dob.year, 8, 17):
        kollam -= 1

    # Kali dinam
    kali_epoch = swe.julday(-3101, 1, 23, 0)
    kali_day = int(swe.julday(dob.year, dob.month, dob.day, 0) - kali_epoch)

    # Star from DB
    star_num = hp.pr_star or 0
    star_ml = NAK_ML[star_num - 1] if 1 <= star_num <= 27 else '—'
    star_pada = hp.pr_pada or '—'
    dasa_lord = DASA_LORD_ML[star_num] if 1 <= star_num <= 27 else '—'
    dasa_disp = _get_dasa_display(hp.pr_dasabalance)

    # TOB display
    tob_display = str(hp.pr_tob)[:5] if hp.pr_tob else '—'

    # Lagnam/Moon for paragraph
    lagnam_rasi_ml = lagnam_row['rasi_ml']
    moon_rasi_ml = planet_rows[1]['rasi_ml']  # index 1 = Chandran

    # Chart rows from DB strings
    rasi_rows = build_chart_rows(hp.pr_rasi)
    amsa_rows = build_chart_rows(hp.pr_amsa)
    bhav_rows = build_chart_rows(hp.pr_bhav)

    # Center cell data for Rasi chart (matches admin porutham chart centre panel)
    rasi_center = _build_rasi_center(
        hp, star_ml, star_pada, dasa_lord, dasa_disp,
    )

    return {
        'hp': hp,
        'dob_display': dob.strftime('%d-%m-%Y'),
        'tob_display': tob_display,
        'ayanamsa': ayan_display,
        'planet_table': full_planet_table,
        'tithi': tithi_display,
        'yoga': YOGA_ML[yoga_idx],
        'karana': KARANA_ML[karana_i],
        'weekday_ml': wd_ml,
        'ayanam': ayanam,
        'season': season,
        'mal_month': mal_month,
        'kollam_year': kollam,
        'kali_dinam': kali_day,
        'star_ml': star_ml,
        'star_pada': star_pada,
        'dasa_lord_ml': dasa_lord,
        'dasa_display': dasa_disp,
        'lagnam_rasi_ml': lagnam_rasi_ml,
        'moon_rasi_ml': moon_rasi_ml,
        'rasi_rows': rasi_rows,
        'amsa_rows': amsa_rows,
        'bhav_rows': bhav_rows,
        'rasi_center': rasi_center,
        'sunrise': sunrise_s,
        'sunset': sunset_s,
        'lat': lat,
        'lon': lon,
    }


def generate_thalakkuri_pdf(hp):
    from django.template.loader import render_to_string
    ctx = calculate_all(hp)
    html = render_to_string('astrology/thalakkuri.html', ctx)
    try:
        from weasyprint import HTML, CSS
        font_css = CSS(string='''
            @font-face {
                font-family: "Noto Sans Malayalam";
                src: local("Noto Sans Malayalam");
            }
            body { font-family: "Noto Sans Malayalam", serif; }
        ''')
        pdf = HTML(string=html, base_url=None).write_pdf(stylesheets=[font_css])
        return pdf, 'pdf'
    except Exception as e:
        print(f'weasyprint error: {e}')
        return html.encode('utf-8'), 'html'
