"""Incomplete profiles must appear in My Matches and open via View Profile."""
from datetime import date, timedelta

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from matches.services import preferred_match_queryset
from profiles.models import UserProfile
from profiles.utils import is_profile_visible_to_others


LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "incomplete-matches-tests",
    }
}


def _years_ago(years):
    return date.today() - timedelta(days=365 * years)


def _user(*, mobile, gender, dob=None, complete=False):
    user = User.objects.create_user(
        mobile=mobile,
        password="x",
        role="user",
        gender=gender,
        dob=dob or _years_ago(28),
        is_active=True,
    )
    if complete:
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


@override_settings(CACHES=LOCMEM_CACHES)
class IncompleteProfilesInMatchesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.viewer = _user(mobile="9120000001", gender="M", complete=True)
        self.incomplete = _user(mobile="9120000002", gender="F", complete=False)
        self.complete = _user(mobile="9120000003", gender="F", complete=True)
        self.client.force_authenticate(user=self.viewer)

    def test_preferred_queryset_includes_incomplete_opposite_gender(self):
        ids = set(preferred_match_queryset(self.viewer).values_list("pk", flat=True))
        self.assertIn(self.incomplete.pk, ids)
        self.assertIn(self.complete.pk, ids)

    def test_matches_list_includes_incomplete_profile(self):
        res = self.client.get("/api/v1/matches/", {"page": 1, "limit": 20})
        self.assertEqual(res.status_code, 200)
        matri_ids = {row["matri_id"] for row in res.data["data"]["profiles"]}
        self.assertIn(self.incomplete.matri_id, matri_ids)
        self.assertIn(self.complete.matri_id, matri_ids)

    def test_dashboard_kpi_counts_incomplete_profiles(self):
        res = self.client.get("/api/v1/dashboard/summary/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["data"]["new_matches"], 2)

    def test_view_profile_allows_incomplete_member(self):
        self.assertTrue(is_profile_visible_to_others(self.incomplete))
        res = self.client.get(f"/api/v1/profiles/{self.incomplete.matri_id}/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data.get("success"))
        self.assertEqual(res.data["data"]["profile"]["matri_id"], self.incomplete.matri_id)
