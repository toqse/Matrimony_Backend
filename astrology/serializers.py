from rest_framework import serializers

from .charts import (
    build_horoscope_charts,
    dasa_lord,
    format_dasa_balance,
    lagnam_name,
    moon_rasi_name,
    star_name,
)
from .models import AstrologyPdfCredit, HoroscopeProfile


class HoroscopeProfileSerializer(serializers.ModelSerializer):
    pr_dob = serializers.DateField(format='%d-%m-%Y', read_only=True)
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
        read_only_fields = [f for f in fields if f != 'pr_dob']

    def get_star_display(self, obj):
        return obj.star_name or star_name(obj.pr_star)

    def get_dasa_display(self, obj):
        return format_dasa_balance(obj.pr_dasabalance).get('balance_text', '')

    def get_lagnam_display(self, obj):
        return obj.lagnam or lagnam_name(obj.pr_rasi)

    def get_rasi_display(self, obj):
        return obj.rasi_sign or moon_rasi_name(obj.pr_rasi)

    def get_dasa_lord(self, obj):
        return dasa_lord(obj.pr_star)

    def get_charts(self, obj):
        return build_horoscope_charts(obj)


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
        return obj.star_name or star_name(obj.pr_star)

    def get_dasa_display(self, obj):
        return format_dasa_balance(obj.pr_dasabalance).get('balance_text', '')

    def get_lagnam_display(self, obj):
        return obj.lagnam or lagnam_name(obj.pr_rasi)

    def get_rasi_display(self, obj):
        return obj.rasi_sign or moon_rasi_name(obj.pr_rasi)

    def get_dasa_lord(self, obj):
        return dasa_lord(obj.pr_star)

    def get_charts(self, obj):
        return build_horoscope_charts(obj)


class PoruthamCheckRequestSerializer(serializers.Serializer):
    matri_id = serializers.CharField(max_length=20, trim_whitespace=True)
    partner_matri_id = serializers.CharField(max_length=20, trim_whitespace=True)


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
