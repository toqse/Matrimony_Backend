from rest_framework import serializers


class PanelPoruthamRequestSerializer(serializers.Serializer):
    bride_profile_id = serializers.IntegerField(min_value=1)
    groom_profile_id = serializers.IntegerField(min_value=1)


class PanelSavePoruthamMatchesSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=['fixed-bride', 'fixed-groom', 'fixed_bride', 'fixed_groom'])
    fixed_profile_id = serializers.IntegerField(min_value=1)
    partner_profile_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=100,
    )


class PanelDeleteSavedPoruthamSerializer(serializers.Serializer):
    fixed_profile_id = serializers.IntegerField(min_value=1)
    partner_profile_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=100,
    )
