from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from admin_panel.branches.models import Branch

PUBLIC_URL = "/api/v1/website/branches/"

LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "website-branches-tests",
    }
}


def _branch(**kwargs):
    defaults = {
        "name": "Cherthala",
        "code": "CHT01",
        "city": "Cherthala",
        "phone": "7907240062",
        "email": "cherthala@test.invalid",
        "address": "Near Private Bus Stand, Cherthala – 688524",
        "is_active": True,
        "is_deleted": False,
    }
    defaults.update(kwargs)
    return Branch.objects.create(**defaults)


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    CACHES=LOCMEM_CACHES,
)
class PublicBranchListTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_lists_active_branches_without_token(self):
        _branch()
        _branch(
            name="Pothanicad",
            code="POT01",
            city="Moovattupuzha",
            phone="6282857276",
            email="pothanicad@test.invalid",
            address="Pothanicad, Moovattupuzha, Ernakulam",
        )
        res = self.client.get(PUBLIC_URL)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data.get("success"))
        rows = res.data["data"]
        self.assertEqual(len(rows), 2)
        names = {row["name"] for row in rows}
        self.assertEqual(names, {"Cherthala", "Pothanicad"})
        first = rows[0]
        self.assertEqual(
            set(first.keys()),
            {"id", "name", "city", "phone", "email", "address"},
        )
        self.assertNotIn("revenue", first)
        self.assertNotIn("profiles_count", first)
        self.assertTrue(first["phone"].startswith("+91"))

    def test_excludes_inactive_and_deleted_branches(self):
        _branch()
        _branch(
            name="Inactive",
            code="INA01",
            email="inactive@test.invalid",
            is_active=False,
        )
        _branch(
            name="Deleted",
            code="DEL01",
            email="deleted@test.invalid",
            is_deleted=True,
        )
        res = self.client.get(PUBLIC_URL)
        self.assertEqual(res.status_code, 200)
        names = [row["name"] for row in res.data["data"]]
        self.assertEqual(names, ["Cherthala"])
