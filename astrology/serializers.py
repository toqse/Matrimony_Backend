from rest_framework import serializers

from .models import AstrologyPdfCredit, HoroscopeProfile


# ── Lookup tables ─────────────────────────────────────────────────────
RASI_NAMES = [
    '', 'Medam', 'Edavam', 'Midhunam', 'Kadakam', 'Chingam', 'Kanni',
    'Thulam', 'Vrischikam', 'Dhanu', 'Makaram', 'Kumbham', 'Meenam',
]

STAR_NAMES = [
    '', 'Ashwini', 'Bharani', 'Karthika', 'Rohini', 'Mrigasira',
    'Thiruvathira', 'Punartham', 'Pooyam', 'Ayilyam', 'Makam',
    'Pooram', 'Uthram', 'Atham', 'Chithra', 'Chothi', 'Vishakam',
    'Anizham', 'Thrikketta', 'Moolam', 'Pooradam', 'Uthradam',
    'Thiruvonam', 'Avittam', 'Chathayam', 'Pooruruttathi',
    'Uthuruttathi', 'Revathi',
]

# Vimshottari dasa lord per nakshatra (1-27); 9-lord cycle repeats 3 times.
DASA_LORDS = [
    '', 'Ketu', 'Venus', 'Sun', 'Moon', 'Mars',
    'Rahu', 'Jupiter', 'Saturn', 'Mercury',
    'Ketu', 'Venus', 'Sun', 'Moon', 'Mars',
    'Rahu', 'Jupiter', 'Saturn', 'Mercury',
    'Ketu', 'Venus', 'Sun', 'Moon', 'Mars',
    'Rahu', 'Jupiter', 'Saturn', 'Mercury',
]

LETTER_TO_SIGN = {c: i + 1 for i, c in enumerate('ABCDEFGHIJKL')}

# Planet order inside the 11-char EXE chart strings (index -> planet).
PLANET_KEYS = [
    ('la', 'Lagnam'),
    ('su', 'Sun'),
    ('mo', 'Moon'),
    ('ma', 'Mars'),
    ('me', 'Mercury'),
    ('ju', 'Jupiter'),
    ('ve', 'Venus'),
    ('sa', 'Saturn'),
    ('ra', 'Rahu'),
    ('ke', 'Ketu'),
    ('md', 'Maandi'),
]

PLANET_ABBR_ML = {
    'la': 'ല', 'su': 'ര', 'mo': 'ച', 'ma': 'കു',
    'me': 'ബു', 'ju': 'ഗു', 've': 'ശു', 'sa': 'ശ',
    'ra': 'രാ', 'ke': 'കേ', 'md': 'മ',
}

PLANET_ABBR_EN = {
    'la': 'La', 'su': 'Ra', 'mo': 'Ch', 'ma': 'Ku',
    'me': 'Bu', 'ju': 'Gu', 've': 'Sk', 'sa': 'Sn',
    'ra': 'Ra', 'ke': 'Ke', 'md': 'Md',
}


# ── Helper functions (compute on-read from raw EXE fields) ────────────
# These NEVER check is_calculated. If the EXE has written pr_rasi / pr_star,
# the values are computed directly so the website shows them immediately.

def _get_star_name(pr_star):
    """Star name from pr_star (1-27). Works regardless of is_calculated."""
    if pr_star and 1 <= pr_star <= 27:
        return STAR_NAMES[pr_star]
    return ''


def _get_dasa_days_to_text(pr_dasabalance):
    """
    Convert raw dasa-balance days to 'XXy XXm XXd'. Uses the Windows EXE formula.

    Examples: 491 -> '01y 04m 04d', 2459 -> '06y 08m 25d'.
    """
    if not pr_dasabalance or pr_dasabalance <= 0:
        return ''
    days = pr_dasabalance
    years = int(days / 365.25)
    rem = days - (years * 365)
    months = int(rem / 30.4375)
    day_rem = int(rem - (months * 30.4375))
    return f'{years:02d}y {months:02d}m {day_rem:02d}d'


def _get_dasa_lord(pr_star):
    """Vimshottari dasa lord from pr_star (1-27). Works regardless of is_calculated."""
    if pr_star and 1 <= pr_star <= 27:
        return DASA_LORDS[pr_star]
    return ''


def _get_rasi_name_from_letter(letter):
    """Convert a chart letter (A-L) to a rasi name."""
    if not letter:
        return ''
    sign = LETTER_TO_SIGN.get(letter.upper())
    if sign and 1 <= sign <= 12:
        return RASI_NAMES[sign]
    return ''


def _get_lagnam_from_rasi_string(pr_rasi):
    """Lagnam name from pr_rasi. Position 0 = Lagnam."""
    if pr_rasi and len(pr_rasi) >= 1:
        return _get_rasi_name_from_letter(pr_rasi[0])
    return ''


def _get_rasi_sign_from_rasi_string(pr_rasi):
    """Moon rasi name from pr_rasi. Position 2 = Moon (Chandran)."""
    if pr_rasi and len(pr_rasi) >= 3:
        return _get_rasi_name_from_letter(pr_rasi[2])
    return ''


def _build_chart(chart_string):
    """
    Convert an 11-char chart string (pr_rasi / pr_amsa / pr_bhav) into a
    house/planet structure for the UI. Returns None when the string is empty
    or malformed. NEVER checks is_calculated.
    """
    if not chart_string or len(chart_string) < 11:
        return None

    houses = {str(i): [] for i in range(1, 13)}
    planets = []
    lagna_sign = None

    for idx, (key, name) in enumerate(PLANET_KEYS):
        letter = chart_string[idx].upper()
        sign = LETTER_TO_SIGN.get(letter)
        if not sign:
            continue

        if key == 'la':
            lagna_sign = sign

        planets.append({
            'index': idx,
            'key': key,
            'abbr_ml': PLANET_ABBR_ML[key],
            'abbr_en': PLANET_ABBR_EN[key],
            'abbr': PLANET_ABBR_EN[key],
            'name': name,
            'sign': sign,
            'sign_name': RASI_NAMES[sign],
        })
        houses[str(sign)].append({
            'key': key,
            'abbr_ml': PLANET_ABBR_ML[key],
            'abbr_en': PLANET_ABBR_EN[key],
            'abbr': PLANET_ABBR_EN[key],
            'name': name,
        })

    return {
        'lagna_sign': lagna_sign,
        'sign_names': {str(i): RASI_NAMES[i] for i in range(1, 13)},
        'houses': houses,
        'planets': planets,
    }


def _build_charts_payload(obj):
    """Assemble rasi/amsa/bhava charts plus star and dasa metadata for one record."""
    return {
        'rasi': _build_chart(obj.pr_rasi),
        'amsa': _build_chart(obj.pr_amsa),
        'bhava': _build_chart(obj.pr_bhav),
        'star': {
            'number': obj.pr_star,
            'name': _get_star_name(obj.pr_star),
            'pada': obj.pr_pada,
        },
        'dasa': {
            'lord': _get_dasa_lord(obj.pr_star),
            'balance_days': obj.pr_dasabalance,
            'balance_text': _get_dasa_days_to_text(obj.pr_dasabalance),
        },
    }


class HoroscopeProfileSerializer(serializers.ModelSerializer):
    star_display = serializers.SerializerMethodField()
    dasa_display = serializers.SerializerMethodField()
    lagnam_display = serializers.SerializerMethodField()
    rasi_display = serializers.SerializerMethodField()
    dasa_lord = serializers.SerializerMethodField()
    charts = serializers.SerializerMethodField()

    class Meta:
        model = HoroscopeProfile
        fields = [
            'id',
            'pr_name',
            'pr_dob',
            'pr_tob',
            'pr_lat',
            'pr_lon',
            'pr_tz',
            'pr_rasi',
            'pr_amsa',
            'pr_bhav',
            'pr_star',
            'pr_pada',
            'pr_dasabalance',
            'lagnam',
            'rasi_sign',
            'star_name',
            'nakshatra_pada',
            'gana',
            'yoni',
            'rajju',
            'is_calculated',
            'calculated_at',
            'created_at',
            'updated_at',
            'star_display',
            'dasa_display',
            'lagnam_display',
            'rasi_display',
            'dasa_lord',
            'charts',
        ]
        read_only_fields = fields

    def get_star_display(self, obj):
        return obj.star_name or _get_star_name(obj.pr_star)

    def get_dasa_display(self, obj):
        return _get_dasa_days_to_text(obj.pr_dasabalance)

    def get_lagnam_display(self, obj):
        return obj.lagnam or _get_lagnam_from_rasi_string(obj.pr_rasi)

    def get_rasi_display(self, obj):
        return obj.rasi_sign or _get_rasi_sign_from_rasi_string(obj.pr_rasi)

    def get_dasa_lord(self, obj):
        return _get_dasa_lord(obj.pr_star)

    def get_charts(self, obj):
        return _build_charts_payload(obj)


class HoroscopeProfilePublicSerializer(serializers.ModelSerializer):
    """Member-visible horoscope summary (no exact birth coordinates or clock time)."""

    star_display = serializers.SerializerMethodField()
    dasa_display = serializers.SerializerMethodField()
    lagnam_display = serializers.SerializerMethodField()
    rasi_display = serializers.SerializerMethodField()
    dasa_lord = serializers.SerializerMethodField()
    charts = serializers.SerializerMethodField()

    class Meta:
        model = HoroscopeProfile
        fields = [
            'pr_rasi',
            'pr_star',
            'pr_pada',
            'pr_dasabalance',
            'lagnam',
            'rasi_sign',
            'star_name',
            'nakshatra_pada',
            'gana',
            'yoni',
            'rajju',
            'is_calculated',
            'calculated_at',
            'star_display',
            'dasa_display',
            'lagnam_display',
            'rasi_display',
            'dasa_lord',
            'charts',
        ]
        read_only_fields = fields

    def get_star_display(self, obj):
        return obj.star_name or _get_star_name(obj.pr_star)

    def get_dasa_display(self, obj):
        return _get_dasa_days_to_text(obj.pr_dasabalance)

    def get_lagnam_display(self, obj):
        return obj.lagnam or _get_lagnam_from_rasi_string(obj.pr_rasi)

    def get_rasi_display(self, obj):
        return obj.rasi_sign or _get_rasi_sign_from_rasi_string(obj.pr_rasi)

    def get_dasa_lord(self, obj):
        return _get_dasa_lord(obj.pr_star)

    def get_charts(self, obj):
        return _build_charts_payload(obj)


class PoruthamCheckRequestSerializer(serializers.Serializer):
    bride_id = serializers.IntegerField(min_value=1)
    groom_id = serializers.IntegerField(min_value=1)


class PoruthamResultSerializer(serializers.Serializer):
    poruthams = serializers.DictField(child=serializers.BooleanField())
    koota_points = serializers.DictField(child=serializers.FloatField(), required=False)
    score = serializers.FloatField()
    max_score = serializers.FloatField()
    result = serializers.CharField()


class AstrologyPdfOrderSerializer(serializers.Serializer):
    product = serializers.ChoiceField(choices=AstrologyPdfCredit.PRODUCT_CHOICES)


class AstrologyPdfVerifySerializer(serializers.Serializer):
    product = serializers.ChoiceField(choices=AstrologyPdfCredit.PRODUCT_CHOICES)
    razorpay_order_id = serializers.CharField(max_length=64, trim_whitespace=True)
    razorpay_payment_id = serializers.CharField(max_length=64, trim_whitespace=True)
    razorpay_signature = serializers.CharField(max_length=512, trim_whitespace=True)
