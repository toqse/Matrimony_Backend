from rest_framework import serializers


class PanelPoruthamRequestSerializer(serializers.Serializer):
    bride_profile_id = serializers.IntegerField(min_value=1)
    groom_profile_id = serializers.IntegerField(min_value=1)
