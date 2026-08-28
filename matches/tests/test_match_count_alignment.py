"""Dashboard new_matches KPI must match unfiltered My Matches total."""
from datetime import date, timedelta

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from profiles.models import UserProfile, UserReligion


def _years_ago(years):
    return date.today() - timedelta(days=365 * years)


def _visible_user(*, mobile, gender, dob=None, is_active=True):
    user = User.objects.create_user(
        mobile=mobile,
        password="x",
        role="user",
        gender=gender,
        dob=dob,
        is_active=is_active,
    )
    UserProfile.objects.create(
        user=user,
        location_completed=True,
        religion_completed=True,
        personal_completed=True,
        family_completed=True,
        education_completed=True,
        about_completed=True,
        photos_completed=True,
    )
    return user


class NewMatchesKpiAlignmentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.viewer = _visible_user(
            mobile="9110000001",
            gender="M",
            dob=_years_ago(32),
        )
        UserReligion.objects.create(
            user=self.viewer,
            partner_age_from=28,
            partner_age_to=35,
        )
        self.in_range = _visible_user(
            mobile="9110000002",
            gender="F",
            dob=_years_ago(30),
        )
        self.too_young = _visible_user(
            mobile="9110000003",
            gender="F",
            dob=_years_ago(22),
        )
        self.too_old = _visible_user(
            mobile="9110000004",
            gender="F",
            dob=_years_ago(45),
        )
        self.client.force_authenticate(user=self.viewer)

    def _summary_count(self):
        res = self.client.get("/api/v1/dashboard/summary/")
        self.assertEqual(res.status_code, 200)
        return res.data["data"]["new_matches"]

    def _matches_total(self, **params):
        res = self.client.get("/api/v1/matches/", params)
        self.assertEqual(res.status_code, 200)
        return res.data["data"]["total_profiles"]

    def test_kpi_matches_unfiltered_matches_total_with_age_preference(self):
        kpi = self._summary_count()
        matches_total = self._matches_total(page=1, limit=10)
        self.assertEqual(kpi, matches_total)
        self.assertEqual(kpi, 1)

    def test_kpi_matches_unfiltered_total_when_age_preference_cleared(self):
        rel = self.viewer.user_religion
        rel.partner_age_from = None
        rel.partner_age_to = None
        rel.save(update_fields=["partner_age_from", "partner_age_to"])

        kpi = self._summary_count()
        matches_total = self._matches_total(page=1, limit=10)
        self.assertEqual(kpi, matches_total)
        self.assertEqual(kpi, 3)
