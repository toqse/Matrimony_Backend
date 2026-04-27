from django.test import TestCase

from accounts.models import User
from master.models import Caste, Religion
from matches.views import _apply_partner_preference
from profiles.models import UserReligion
from profiles.serializers import PartnerPreferencesUpdateSerializer


class PartnerCastePreferenceSerializerTests(TestCase):
    def setUp(self):
        self.rel_hindu = Religion.objects.create(name='Hindu', is_active=True)
        self.rel_christian = Religion.objects.create(name='Christian', is_active=True)
        self.caste_brahmin = Caste.objects.create(religion=self.rel_hindu, name='Brahmin', is_active=True)
        self.caste_nair = Caste.objects.create(religion=self.rel_hindu, name='Nair', is_active=True)
        self.caste_rc = Caste.objects.create(religion=self.rel_christian, name='Roman Catholic', is_active=True)
        self.user = User.objects.create_user(mobile='9000000001', password='x', role='user')
        self.user_rel = UserReligion.objects.create(user=self.user, religion=self.rel_hindu)

    def test_open_to_all_clears_religion_and_caste_preferences(self):
        serializer = PartnerPreferencesUpdateSerializer(
            data={
                'partner_preference_type': UserReligion.PARTNER_PREFERENCE_ALL,
                'partner_religion_ids': [self.rel_hindu.id],
                'partner_caste_preferences': {str(self.rel_hindu.id): [self.caste_brahmin.id]},
            },
            partial=True,
            context={'user': self.user, 'existing_obj': self.user_rel},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['partner_religion_ids'], [])
        self.assertEqual(serializer.validated_data['partner_caste_preferences'], {})

    def test_specific_religions_rejects_caste_map_keys_outside_selection(self):
        serializer = PartnerPreferencesUpdateSerializer(
            data={
                'partner_preference_type': UserReligion.PARTNER_PREFERENCE_SPECIFIC,
                'partner_religion_ids': [self.rel_hindu.id],
                'partner_caste_preferences': {str(self.rel_christian.id): [self.caste_rc.id]},
            },
            partial=True,
            context={'user': self.user, 'existing_obj': self.user_rel},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('partner_caste_preferences', serializer.errors)


class PartnerCastePreferenceMatchFilterTests(TestCase):
    def setUp(self):
        self.rel_hindu = Religion.objects.create(name='Hindu', is_active=True)
        self.rel_christian = Religion.objects.create(name='Christian', is_active=True)
        self.caste_brahmin = Caste.objects.create(religion=self.rel_hindu, name='Brahmin', is_active=True)
        self.caste_nair = Caste.objects.create(religion=self.rel_hindu, name='Nair', is_active=True)
        self.caste_rc = Caste.objects.create(religion=self.rel_christian, name='Roman Catholic', is_active=True)

        self.viewer = User.objects.create_user(mobile='9000000002', password='x', role='user', gender='M')
        self.viewer_rel = UserReligion.objects.create(
            user=self.viewer,
            religion=self.rel_hindu,
            partner_preference_type=UserReligion.PARTNER_PREFERENCE_SPECIFIC,
            partner_religion_ids=[self.rel_hindu.id, self.rel_christian.id],
            partner_caste_preferences={
                str(self.rel_hindu.id): [self.caste_brahmin.id],
            },
        )

        self.match_hindu_brahmin = User.objects.create_user(
            mobile='9000000003', password='x', role='user', gender='F'
        )
        UserReligion.objects.create(
            user=self.match_hindu_brahmin,
            religion=self.rel_hindu,
            caste_fk=self.caste_brahmin,
        )

        self.match_hindu_nair = User.objects.create_user(
            mobile='9000000004', password='x', role='user', gender='F'
        )
        UserReligion.objects.create(
            user=self.match_hindu_nair,
            religion=self.rel_hindu,
            caste_fk=self.caste_nair,
        )

        self.match_christian = User.objects.create_user(
            mobile='9000000005', password='x', role='user', gender='F'
        )
        UserReligion.objects.create(
            user=self.match_christian,
            religion=self.rel_christian,
            caste_fk=self.caste_rc,
        )

    def test_specific_religion_mode_applies_per_religion_caste_filters(self):
        qs = User.objects.filter(pk__in=[
            self.match_hindu_brahmin.pk,
            self.match_hindu_nair.pk,
            self.match_christian.pk,
        ])
        filtered = _apply_partner_preference(qs, self.viewer_rel)
        self.assertSetEqual(
            set(filtered.values_list('pk', flat=True)),
            {self.match_hindu_brahmin.pk, self.match_christian.pk},
        )
