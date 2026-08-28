from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from admin_panel.auth.models import AdminUser
from master.models import City, Country, District, State
from profiles.models import UserLocation

LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "location-admin-crud-tests",
    }
}

COUNTRIES = "/api/v1/admin/master/countries/"
STATES = "/api/v1/admin/master/states/"
DISTRICTS = "/api/v1/admin/master/districts/"
CITIES = "/api/v1/admin/master/cities/"


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    CACHES=LOCMEM_CACHES,
)
class LocationMasterCRUDTests(TestCase):
    def setUp(self):
        self.admin = AdminUser.objects.create(
            mobile="+919900000401",
            role=AdminUser.ROLE_ADMIN,
            name="Location Admin",
            is_active=True,
        )
        self.staff = AdminUser.objects.create(
            mobile="+919900000402",
            role=AdminUser.ROLE_STAFF,
            name="Location Staff",
            is_active=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

        self.country = Country.objects.create(name="India", code="IN", is_active=True)
        self.state = State.objects.create(country=self.country, name="Kerala", code="KL", is_active=True)
        self.district = District.objects.create(state=self.state, name="Ernakulam", is_active=True)
        self.city = City.objects.create(district=self.district, name="Kochi", is_active=True)

    def test_list_countries(self):
        res = self.client.get(COUNTRIES)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["success"])
        names = [row["name"] for row in res.data["data"]["results"]]
        self.assertIn("India", names)

    def test_create_and_update_country(self):
        res = self.client.post(COUNTRIES, {"name": "UAE", "code": "AE"}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        pk = res.data["data"]["id"]
        self.assertEqual(res.data["data"]["name"], "UAE")

        res = self.client.patch(f"{COUNTRIES}{pk}/", {"name": "United Arab Emirates"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["data"]["name"], "United Arab Emirates")

    def test_country_name_uniqueness(self):
        res = self.client.post(COUNTRIES, {"name": "india"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("already exists", res.data["error"]["message"])

    def test_staff_cannot_create_country(self):
        self.client.force_authenticate(user=self.staff)
        res = self.client.post(COUNTRIES, {"name": "Nepal"}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_unauthenticated_list_returns_401(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(COUNTRIES)
        self.assertEqual(res.status_code, 401)

    def test_states_require_country_id(self):
        res = self.client.get(STATES)
        self.assertEqual(res.status_code, 400)

    def test_create_list_update_state(self):
        res = self.client.post(
            STATES,
            {"name": "Tamil Nadu", "code": "TN", "country": self.country.id},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        pk = res.data["data"]["id"]

        res = self.client.get(f"{STATES}?country_id={self.country.id}")
        self.assertEqual(res.status_code, 200)
        names = [row["name"] for row in res.data["data"]["results"]]
        self.assertIn("Tamil Nadu", names)
        self.assertIn("Kerala", names)

        res = self.client.patch(f"{STATES}{pk}/", {"name": "Tamilnadu"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["data"]["name"], "Tamilnadu")

    def test_state_uniqueness_under_country(self):
        res = self.client.post(
            STATES,
            {"name": "kerala", "country": self.country.id},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("already exists", res.data["error"]["message"])

    def test_create_district_and_city(self):
        res = self.client.post(
            DISTRICTS,
            {"name": "Thrissur", "state": self.state.id},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        district_id = res.data["data"]["id"]

        res = self.client.post(
            CITIES,
            {"name": "Guruvayur", "district": district_id},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)

        res = self.client.get(f"{CITIES}?district_id={district_id}")
        self.assertEqual(res.status_code, 200)
        names = [row["name"] for row in res.data["data"]["results"]]
        self.assertIn("Guruvayur", names)

    def test_parent_dropdowns(self):
        res = self.client.get(f"{STATES}countries/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(any(row["name"] == "India" for row in res.data["data"]))

        res = self.client.get(f"{DISTRICTS}states/?country_id={self.country.id}")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(any(row["name"] == "Kerala" for row in res.data["data"]))

        res = self.client.get(f"{CITIES}districts/?state_id={self.state.id}")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(any(row["name"] == "Ernakulam" for row in res.data["data"]))

    def test_delete_blocked_when_profile_uses_country(self):
        member = User.objects.create_user(mobile="9300000401", password="x", role="user")
        UserLocation.objects.create(user=member, country=self.country)

        res = self.client.delete(f"{COUNTRIES}{self.country.id}/")
        self.assertEqual(res.status_code, 400)
        self.assertIn("used by", res.data["error"]["message"])
        self.country.refresh_from_db()
        self.assertTrue(self.country.is_active)

    def test_soft_delete_country_cascades_descendants(self):
        extra_state = State.objects.create(country=self.country, name="Karnataka", is_active=True)
        extra_district = District.objects.create(state=extra_state, name="Bengaluru", is_active=True)
        extra_city = City.objects.create(district=extra_district, name="Whitefield", is_active=True)

        res = self.client.delete(f"{COUNTRIES}{self.country.id}/")
        self.assertEqual(res.status_code, 200, res.data)

        self.country.refresh_from_db()
        self.state.refresh_from_db()
        self.district.refresh_from_db()
        self.city.refresh_from_db()
        extra_state.refresh_from_db()
        extra_district.refresh_from_db()
        extra_city.refresh_from_db()

        self.assertFalse(self.country.is_active)
        self.assertFalse(self.state.is_active)
        self.assertFalse(self.district.is_active)
        self.assertFalse(self.city.is_active)
        self.assertFalse(extra_state.is_active)
        self.assertFalse(extra_district.is_active)
        self.assertFalse(extra_city.is_active)

        res = self.client.get(COUNTRIES)
        names = [row["name"] for row in res.data["data"]["results"]]
        self.assertNotIn("India", names)

    def test_soft_delete_city(self):
        res = self.client.delete(f"{CITIES}{self.city.id}/")
        self.assertEqual(res.status_code, 200)
        self.city.refresh_from_db()
        self.assertFalse(self.city.is_active)
