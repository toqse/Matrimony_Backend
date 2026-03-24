from rest_framework import serializers

from .models import Horoscope


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


class HoroscopeGenerateRequestSerializer(serializers.Serializer):
    profile_id = serializers.IntegerField(min_value=1)


class PoruthamCheckRequestSerializer(serializers.Serializer):
    bride_id = serializers.IntegerField(min_value=1)
    groom_id = serializers.IntegerField(min_value=1)


class PoruthamResultSerializer(serializers.Serializer):
    poruthams = serializers.DictField(child=serializers.BooleanField())
    score = serializers.IntegerField()
    max_score = serializers.IntegerField()
    result = serializers.CharField()
