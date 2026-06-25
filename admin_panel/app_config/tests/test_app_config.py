from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from admin_panel.app_config.models import MobileAppConfig
from admin_panel.auth.models import AdminUser

LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "app-config-tests",
    }
}

PUBLIC_URL = "/api/v1/website/app-config/"
ADMIN_URL = "/api/v1/admin/app-config/"


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    CACHES=LOCMEM_CACHES,
)
class AppConfigAPITests(TestCase):
    def setUp(self):
        self.config = MobileAppConfig.load()
        self.config.android_version = "1.0.0"
        self.config.ios_version = "1.0.0"
        self.config.android_force_update = False
        self.config.ios_force_update = False
        self.config.save()

        self.admin = AdminUser.objects.create(
            mobile="+919900000301",
            role=AdminUser.ROLE_ADMIN,
            name="App Config Admin",
            is_active=True,
        )
        self.staff = AdminUser.objects.create(
            mobile="+919900000302",
            role=AdminUser.ROLE_STAFF,
            name="App Config Staff",
            is_active=True,
        )
        self.client = APIClient()

    def test_public_get_without_token(self):
        res = self.client.get(PUBLIC_URL)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data.get("success"))
        data = res.data["data"]
        self.assertEqual(data["android_version"], "1.0.0")
        self.assertEqual(data["ios_version"], "1.0.0")
        self.assertFalse(data["android_force_update"])
        self.assertFalse(data["ios_force_update"])
        self.assertIn("updated_at", data)

    def test_admin_get(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(ADMIN_URL)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data.get("success"))
        self.assertEqual(res.data["data"]["android_version"], "1.0.0")

    def test_admin_patch_partial_update(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(
            ADMIN_URL,
            {"ios_version": "2.0.0", "ios_force_update": True},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.data["data"]
        self.assertEqual(data["ios_version"], "2.0.0")
        self.assertTrue(data["ios_force_update"])
        self.assertEqual(data["android_version"], "1.0.0")

        self.config.refresh_from_db()
        self.assertEqual(self.config.ios_version, "2.0.0")
        self.assertTrue(self.config.ios_force_update)

    def test_admin_patch_without_token_returns_401(self):
        res = self.client.patch(ADMIN_URL, {"ios_version": "2.0.0"}, format="json")
        self.assertEqual(res.status_code, 401)

    def test_admin_patch_staff_returns_403(self):
        self.client.force_authenticate(user=self.staff)
        res = self.client.patch(ADMIN_URL, {"ios_version": "2.0.0"}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_admin_patch_empty_version_returns_400(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(ADMIN_URL, {"android_version": "  "}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.data.get("success"))
