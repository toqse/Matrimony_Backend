"""PATCH /profile/religion/ accepts partner age same as partner-preferences (serializer + DB)."""
from django.test import TestCase

from accounts.models import User
from master.models import Religion
from profiles.models import UserReligion
from profiles.serializers import ReligionDetailsReadSerializer, ReligionDetailsUpdateSerializer


class ReligionPartnerAgeParityTests(TestCase):
    def setUp(self):
        self.rel = Religion.objects.create(name='Hindu', is_active=True)
        self.user = User.objects.create_user(mobile='9200000001', password='x', role='user')
        UserReligion.objects.create(user=self.user, religion=self.rel)

    def test_patch_serializer_updates_partner_age_via_update_or_create(self):
        ser = ReligionDetailsUpdateSerializer(
            data={'partner_age_from': 28, 'partner_age_to': 36},
            partial=True,
            context={'request': type('R', (), {'user': self.user})()},
        )
        self.assertTrue(ser.is_valid(), ser.errors)

        vd = ser.validated_data
        defaults = {
            'partner_religion_preference': vd.get('partner_religion_preference', ''),
        }
        if vd.get('religion_id') is not None:
            defaults['religion_id'] = vd['religion_id']
        if vd.get('caste_id') is not None:
            defaults['caste_fk_id'] = vd['caste_id']
        if vd.get('mother_tongue_id') is not None:
            defaults['mother_tongue_id'] = vd['mother_tongue_id']
        if 'partner_preference_type' in vd:
            defaults['partner_preference_type'] = vd['partner_preference_type']
        if 'partner_religion_ids' in vd:
            defaults['partner_religion_ids'] = vd['partner_religion_ids']
        if 'partner_caste_preferences' in vd:
            defaults['partner_caste_preferences'] = vd['partner_caste_preferences']
        if 'partner_age_from' in vd:
            defaults['partner_age_from'] = vd['partner_age_from']
        if 'partner_age_to' in vd:
            defaults['partner_age_to'] = vd['partner_age_to']

        UserReligion.objects.update_or_create(user=self.user, defaults=defaults)
        rel = UserReligion.objects.get(user=self.user)
        self.assertEqual(rel.partner_age_from, 28)
        self.assertEqual(rel.partner_age_to, 36)

        read = ReligionDetailsReadSerializer(rel).data
        self.assertEqual(read['partner_age_from'], 28)
        self.assertEqual(read['partner_age_to'], 36)
