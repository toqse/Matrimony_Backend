from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from admin_panel.enquiries.models import Enquiry

PUBLIC_URL = "/api/v1/website/enquiries/"

LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "website-enquiries-tests",
    }
}


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    CACHES=LOCMEM_CACHES,
)
class PublicEnquiryCreateTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_creates_website_enquiry_without_token(self):
        res = self.client.post(
            PUBLIC_URL,
            {
                "name": "Arya S J",
                "phone": "9876543210",
                "email": "arya@test.invalid",
                "subject": "Plan question",
                "message": "I would like to know more about Gold plans.",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.data.get("success"))
        self.assertEqual(Enquiry.objects.count(), 1)
        enquiry = Enquiry.objects.get()
        self.assertEqual(enquiry.name, "Arya S J")
        self.assertEqual(enquiry.phone, "+919876543210")
        self.assertEqual(enquiry.email, "arya@test.invalid")
        self.assertEqual(enquiry.source, "website")
        self.assertEqual(enquiry.status, "new")
        self.assertIsNone(enquiry.created_by_id)
        self.assertIsNone(enquiry.assigned_to_id)
        self.assertIn("Plan question", enquiry.notes)
        self.assertIn("Gold plans", enquiry.notes)

    def test_rejects_missing_name_phone_and_message(self):
        res = self.client.post(PUBLIC_URL, {}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.data.get("success"))
        self.assertEqual(Enquiry.objects.count(), 0)

    def test_rejects_invalid_phone(self):
        res = self.client.post(
            PUBLIC_URL,
            {
                "name": "Test User",
                "phone": "12345",
                "message": "Hello there",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.data.get("success"))
        self.assertEqual(Enquiry.objects.count(), 0)

    def test_ignores_assigned_to_from_client(self):
        res = self.client.post(
            PUBLIC_URL,
            {
                "name": "Walk In",
                "phone": "9876501234",
                "message": "Please call me back.",
                "assigned_to": 99,
                "source": "walk-in",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        enquiry = Enquiry.objects.get()
        self.assertEqual(enquiry.source, "website")
        self.assertIsNone(enquiry.assigned_to_id)
