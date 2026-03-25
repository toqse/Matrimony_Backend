from rest_framework import serializers

from .models import AstrologyPdfCredit, Horoscope
from .services.utils import enrich_grahanila_planets


class HoroscopeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Horoscope
        fields = [
            'profile',
            'date_of_birth',
            'time_of_birth',
            'place_of_birth',
            'latitude',
            'longitude',
            'lagna',
            'rasi',
            'nakshatra',
            'nakshatra_pada',
            'gana',
            'yoni',
            'nadi',
            'rajju',
            'grahanila',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        g = data.get('grahanila')
        if g:
            data['grahanila'] = enrich_grahanila_planets(g)
        return data


class HoroscopeGenerateRequestSerializer(serializers.Serializer):
    matri_id = serializers.CharField(max_length=20, trim_whitespace=True)
    partner_matri_id = serializers.CharField(
        max_length=20, required=False, allow_blank=True, trim_whitespace=True
    )


class PoruthamCheckRequestSerializer(serializers.Serializer):
    bride_id = serializers.IntegerField(min_value=1)
    groom_id = serializers.IntegerField(min_value=1)


class PoruthamResultSerializer(serializers.Serializer):
    poruthams = serializers.DictField(child=serializers.BooleanField())
    koota_points = serializers.DictField(child=serializers.FloatField(), required=False)
    score = serializers.FloatField()
    max_score = serializers.FloatField()
    result = serializers.CharField()


class BirthDetailCandidateSerializer(serializers.Serializer):
    """Read-only row for profiles eligible for horoscope (UserProfile + stored_horoscope_exists annotate)."""

    profile_id = serializers.IntegerField(source='pk')
    matri_id = serializers.CharField(source='user.matri_id', allow_null=True)
    name = serializers.CharField(source='user.name', allow_blank=True)
    gender = serializers.CharField(source='user.gender', allow_blank=True)
    has_horoscope = serializers.BooleanField(source='stored_horoscope_exists')


class AstrologyPdfOrderSerializer(serializers.Serializer):
    product = serializers.ChoiceField(choices=AstrologyPdfCredit.PRODUCT_CHOICES)


class AstrologyPdfVerifySerializer(serializers.Serializer):
    product = serializers.ChoiceField(choices=AstrologyPdfCredit.PRODUCT_CHOICES)
    razorpay_order_id = serializers.CharField(max_length=64, trim_whitespace=True)
    razorpay_payment_id = serializers.CharField(max_length=64, trim_whitespace=True)
    razorpay_signature = serializers.CharField(max_length=512, trim_whitespace=True)
