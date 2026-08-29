"""My Matches height filter must include height_text-only profiles."""
from datetime import date, timedelta

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from master.models import Height
from profiles.models import UserPersonal, UserProfile


def _years_ago(years):
    return date.today() - timedelta(days=365 * years)


def _visible_user(*, mobile, gender, name, dob=None):
    user = User.objects.create_user(
        mobile=mobile,
        password="x",
        role="user",
        gender=gender,
        name=name,
        dob=dob or _years_ago(30),
        is_active=True,
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


class MatchHeightFilterTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.viewer = _visible_user(
            mobile="9111000001",
            gender="M",
            name="Viewer",
        )
        self.text_only = _visible_user(
            mobile="9111000002",
            gender="F",
            name="Text Height",
        )
        UserPersonal.objects.create(
            user=self.text_only,
            height_text="165 cm",
        )
        self.fk_tall = _visible_user(
            mobile="9111000003",
            gender="F",
            name="Fk Tall",
        )
        tall = Height.objects.create(value_cm=180, display_label="180 cm")
        UserPersonal.objects.create(user=self.fk_tall, height=tall)
        self.client.force_authenticate(user=self.viewer)

    def _matches(self, **params):
        res = self.client.get("/api/v1/matches/", params)
        self.assertEqual(res.status_code, 200, getattr(res, "data", res.content))
        return res.data["data"]

    def test_height_text_only_profile_is_included_in_range(self):
        data = self._matches(height_min=160, height_max=170, page=1, limit=20)
        names = [p["name"] for p in data["profiles"]]
        self.assertIn("Text Height", names)
        self.assertNotIn("Fk Tall", names)
        self.assertEqual(data["total_profiles"], 1)
        text_row = next(p for p in data["profiles"] if p["name"] == "Text Height")
        self.assertEqual(text_row["height"], 165)

    def test_fk_height_profile_is_included_above_range(self):
        data = self._matches(height_min=175, page=1, limit=20)
        names = [p["name"] for p in data["profiles"]]
        self.assertIn("Fk Tall", names)
        self.assertNotIn("Text Height", names)
        self.assertEqual(data["total_profiles"], 1)

    def test_list_payload_parses_height_text_without_filter(self):
        data = self._matches(page=1, limit=20)
        by_name = {p["name"]: p for p in data["profiles"]}
        self.assertEqual(by_name["Text Height"]["height"], 165)
        self.assertEqual(by_name["Fk Tall"]["height"], 180)
