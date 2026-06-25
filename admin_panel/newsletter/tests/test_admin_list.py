from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from admin_panel.auth.models import AdminUser
from admin_panel.newsletter.models import NewsletterSubscriber

LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "newsletter-admin-list-tests",
    }
}

LIST_URL = "/api/v1/admin/newsletter/"


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    CACHES=LOCMEM_CACHES,
)
class NewsletterAdminListTests(TestCase):
    def setUp(self):
        self.admin = AdminUser.objects.create(
            mobile="+919900000201",
            role=AdminUser.ROLE_ADMIN,
            name="Newsletter Admin",
            is_active=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        NewsletterSubscriber.objects.create(email="one@example.com", source="footer")
        NewsletterSubscriber.objects.create(email="two@example.com", source="footer", is_active=False)

    def test_list_returns_subscribers(self):
        res = self.client.get(LIST_URL)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data.get("success"))
        data = res.data["data"]
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["summary"]["active"], 1)
        self.assertEqual(data["summary"]["inactive"], 1)

    def test_search_filters_by_email(self):
        res = self.client.get(LIST_URL, {"search": "one@"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["data"]["count"], 1)
        self.assertEqual(res.data["data"]["results"][0]["email"], "one@example.com")

    def test_requires_admin(self):
        staff = AdminUser.objects.create(
            mobile="+919900000202",
            role=AdminUser.ROLE_STAFF,
            name="Staff",
            is_active=True,
        )
        client = APIClient()
        client.force_authenticate(user=staff)
        res = client.get(LIST_URL)
        self.assertEqual(res.status_code, 403)
