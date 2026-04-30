"""has_partner_preferences_filled helper used in auth verify response."""
from django.test import TestCase

from accounts.models import User
from master.models import Caste, Religion
from profiles.models import UserReligion
from profiles.utils import has_partner_preferences_filled


class HasPartnerPreferencesFilledTests(TestCase):
    def setUp(self):
        self.rel_hindu = Religion.objects.create(name='Hindu', is_active=True)
        self.rel_christian = Religion.objects.create(name='Christian', is_active=True)
        self.caste_b = Caste.objects.create(religion=self.rel_hindu, name='Brahmin', is_active=True)
        self.user = User.objects.create_user(mobile='9100000001', password='x', role='user')

    def test_no_user_religion_row_false(self):
        self.assertFalse(has_partner_preferences_filled(self.user))

    def test_open_to_all_defaults_false(self):
        UserReligion.objects.create(
            user=self.user,
            religion=self.rel_hindu,
            partner_preference_type=UserReligion.PARTNER_PREFERENCE_ALL,
        )
        self.assertFalse(has_partner_preferences_filled(self.user))

    def test_age_range_true(self):
        UserReligion.objects.create(
            user=self.user,
            religion=self.rel_hindu,
            partner_age_from=25,
            partner_age_to=35,
        )
        self.assertTrue(has_partner_preferences_filled(self.user))

    def test_own_religion_only_true(self):
        UserReligion.objects.create(
            user=self.user,
            religion=self.rel_hindu,
            partner_preference_type=UserReligion.PARTNER_PREFERENCE_OWN,
        )
        self.assertTrue(has_partner_preferences_filled(self.user))

    def test_specific_religions_with_ids_true(self):
        UserReligion.objects.create(
            user=self.user,
            religion=self.rel_hindu,
            partner_preference_type=UserReligion.PARTNER_PREFERENCE_SPECIFIC,
            partner_religion_ids=[self.rel_hindu.id],
        )
        self.assertTrue(has_partner_preferences_filled(self.user))

    def test_caste_map_true_even_if_open_when_map_present(self):
        """Stale data edge: non-empty partner_caste_preferences counts."""
        UserReligion.objects.create(
            user=self.user,
            religion=self.rel_hindu,
            partner_preference_type=UserReligion.PARTNER_PREFERENCE_ALL,
            partner_caste_preferences={str(self.rel_hindu.id): [self.caste_b.id]},
        )
        self.assertTrue(has_partner_preferences_filled(self.user))
