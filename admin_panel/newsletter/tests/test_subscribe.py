from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from admin_panel.newsletter.models import NewsletterSubscriber

SUBSCRIBE_URL = "/api/v1/website/newsletter/subscribe/"

LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "newsletter-subscribe-tests",
    }
}


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    CACHES=LOCMEM_CACHES,
)
class NewsletterSubscribeTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_valid_email_creates_record(self):
        res = self.client.post(SUBSCRIBE_URL, {"email": "Tips@Example.com"}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.data.get("success"))
        self.assertEqual(NewsletterSubscriber.objects.count(), 1)
        self.assertEqual(NewsletterSubscriber.objects.get().email, "tips@example.com")

    def test_duplicate_email_idempotent(self):
        NewsletterSubscriber.objects.create(email="dup@example.com")
        res = self.client.post(SUBSCRIBE_URL, {"email": "dup@example.com"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertIn("already subscribed", res.data["data"]["message"].lower())
        self.assertEqual(NewsletterSubscriber.objects.count(), 1)

    def test_invalid_email_returns_400(self):
        res = self.client.post(SUBSCRIBE_URL, {"email": "not-an-email"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.data.get("success"))
        self.assertEqual(NewsletterSubscriber.objects.count(), 0)

    def test_reactivates_inactive_subscriber(self):
        sub = NewsletterSubscriber.objects.create(email="back@example.com", is_active=False)
        res = self.client.post(SUBSCRIBE_URL, {"email": "back@example.com"}, format="json")
        self.assertEqual(res.status_code, 200)
        sub.refresh_from_db()
        self.assertTrue(sub.is_active)
