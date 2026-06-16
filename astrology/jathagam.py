"""
Jathagam PDF Generator — Kerala style horoscope document.
Direct conversion from VB source. Do not modify logic.
"""
from django.template.loader import render_to_string

from .charts import format_dasa_balance

PLANET_ML = {
    'la': 'ല', 'su': 'ര', 'mo': 'ച', 'ma': 'കു',
    'me': 'ബു', 'ju': 'ഗു', 've': 'ശു', 'sa': 'ശ',
    'ra': 'രാ', 'ke': 'കേ', 'md': 'മ',
}
PLANET_EN = {
    'la': 'Lagnam', 'su': 'Ravi', 'mo': 'Chandran', 'ma': 'Kuja',
    'me': 'Budhan', 'ju': 'Guru', 've': 'Sukran', 'sa': 'Sani',
    'ra': 'Rahu', 'ke': 'Kethu', 'md': 'Maandi',
}
RASI_EN = ['', 'Medam', 'Edavam', 'Midhunam', 'Kadakam', 'Chingam', 'Kanni',
           'Thulam', 'Vrischikam', 'Dhanu', 'Makaram', 'Kumbham', 'Meenam']
RASI_ML = ['', 'മേടം', 'ഇടവം', 'മിഥുനം', 'കർക്കടകം', 'ചിങ്ങം', 'കന്നി',
           'തുലാം', 'വൃശ്ചികം', 'ധനു', 'മകരം', 'കുംഭം', 'മീനം']
STAR_EN = ['', 'Ashwini', 'Bharani', 'Karthika', 'Rohini', 'Mrigasira',
           'Thiruvathira', 'Punartham', 'Pooyam', 'Ayilyam', 'Makam', 'Pooram',
           'Uthram', 'Atham', 'Chithra', 'Chothi', 'Vishakam', 'Anizham',
           'Thrikketta', 'Moolam', 'Pooradam', 'Uthradam', 'Thiruvonam',
           'Avittam', 'Chathayam', 'Pooruruttathi', 'Uthuruttathi', 'Revathi']
STAR_ML = ['', 'അശ്വതി', 'ഭരണി', 'കാർത്തിക', 'രോഹിണി', 'മകയിരം',
           'തിരുവാതിര', 'പുണർതം', 'പൂയം', 'ആയില്യം', 'മകം', 'പൂരം',
           'ഉത്രം', 'അത്തം', 'ചിത്ര', 'ചോതി', 'വിശാഖം', 'അനിഴം',
           'തൃക്കേട്ട', 'മൂലം', 'പൂരാടം', 'ഉത്രാടം', 'തിരുവോണം',
           'അവിട്ടം', 'ചതയം', 'പൂരുരുട്ടാതി', 'ഉത്തൃട്ടാതി', 'രേവതി']
DASA_LORDS = ['', 'Ketu', 'Venus', 'Sun', 'Moon', 'Mars', 'Rahu',
              'Jupiter', 'Saturn', 'Mercury', 'Ketu', 'Venus', 'Sun', 'Moon',
              'Mars', 'Rahu', 'Jupiter', 'Saturn', 'Mercury', 'Ketu', 'Venus',
              'Sun', 'Moon', 'Mars', 'Rahu', 'Jupiter', 'Saturn', 'Mercury']
PLANETS_ORDER = ['la', 'su', 'mo', 'ma', 'me', 'ju', 've', 'sa', 'ra', 'ke', 'md']
LETTER_TO_SIGN = {c: i + 1 for i, c in enumerate('ABCDEFGHIJKL')}


def get_dasa_display(days):
    if not days or days <= 0:
        return '00y 00m 00d'
    return format_dasa_balance(days)['balance_text']


def decode_chart(chart_str):
    """Returns (houses_dict, lagna_sign)."""
    houses = {i: [] for i in range(1, 13)}
    lagna_sign = None
    if not chart_str or len(chart_str) < 11:
        return houses, lagna_sign
    for idx, key in enumerate(PLANETS_ORDER):
        sign = LETTER_TO_SIGN.get(chart_str[idx].upper())
        if sign:
            houses[sign].append(key)
            if key == 'la':
                lagna_sign = sign
    return houses, lagna_sign


def build_grid(houses, lagna_sign):
    """
    Kerala 4x4 chart grid.
    Layout:
      [12][ 1][ 2][ 3]
      [11][  CENTER  ][ 4]
      [10][  CENTER  ][ 5]
      [ 9][ 8][ 7][ 6]
    Returns list of rows; center cells marked with type='center'.
    """
    layout = [
        [12, 1, 2, 3],
        [11, None, None, 4],
        [10, None, None, 5],
        [9, 8, 7, 6],
    ]
    rows = []
    for row in layout:
        cells = []
        for num in row:
            if num is None:
                cells.append({'type': 'center'})
            else:
                cells.append({
                    'type': 'house',
                    'num': num,
                    'planets': [PLANET_ML[p] for p in houses.get(num, [])],
                    'is_lagna': num == lagna_sign,
                })
        rows.append(cells)
    return rows


def build_context(hp):
    """Build template context from HoroscopeProfile object."""
    rasi_h, rasi_l = decode_chart(hp.pr_rasi)
    amsa_h, amsa_l = decode_chart(hp.pr_amsa)
    bhav_h, bhav_l = decode_chart(hp.pr_bhav)

    star = hp.pr_star or 0
    lagnam_sign = LETTER_TO_SIGN.get(hp.pr_rasi[0].upper(), 0) if hp.pr_rasi else 0
    moon_sign = (
        LETTER_TO_SIGN.get(hp.pr_rasi[2].upper(), 0)
        if hp.pr_rasi and len(hp.pr_rasi) > 2
        else 0
    )

    planet_rows = []
    for idx, key in enumerate(PLANETS_ORDER):
        if hp.pr_rasi and len(hp.pr_rasi) > idx:
            s = LETTER_TO_SIGN.get(hp.pr_rasi[idx].upper(), 0)
            planet_rows.append({
                'ml': PLANET_ML[key],
                'en': PLANET_EN[key],
                'rasi_ml': RASI_ML[s] if s else '',
                'rasi_en': RASI_EN[s] if s else '',
            })

    return {
        'hp': hp,
        'dob': hp.pr_dob.strftime('%d-%m-%Y') if hp.pr_dob else '',
        'tob': str(hp.pr_tob)[:5] if hp.pr_tob else '',
        'star_num': star,
        'star_en': STAR_EN[star] if 1 <= star <= 27 else '',
        'star_ml': STAR_ML[star] if 1 <= star <= 27 else '',
        'pada': hp.pr_pada or '',
        'dasa_lord': DASA_LORDS[star] if 1 <= star <= 27 else '',
        'dasa': get_dasa_display(hp.pr_dasabalance),
        'lagnam_ml': RASI_ML[lagnam_sign] if lagnam_sign else '',
        'lagnam_en': RASI_EN[lagnam_sign] if lagnam_sign else '',
        'rasi_ml': RASI_ML[moon_sign] if moon_sign else '',
        'rasi_en': RASI_EN[moon_sign] if moon_sign else '',
        'rasi_rows': build_grid(rasi_h, rasi_l),
        'amsa_rows': build_grid(amsa_h, amsa_l),
        'bhav_rows': build_grid(bhav_h, bhav_l),
        'planet_rows': planet_rows,
    }


def generate_pdf(hp):
    """
    Generate Jathagam PDF bytes.
    Falls back to HTML bytes if weasyprint is unavailable.
    """
    html = render_to_string('astrology/jathagam.html', build_context(hp))
    try:
        from weasyprint import HTML
        return HTML(string=html, base_url=None).write_pdf(), 'pdf'
    except Exception:
        return html.encode('utf-8'), 'html'
