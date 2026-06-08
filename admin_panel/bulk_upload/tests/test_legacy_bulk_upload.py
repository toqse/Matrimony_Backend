"""Tests for the legacy-format bulk upload flow.

Covers:
- Header detection: legacy fingerprints (`mother toungue`, `horochart`, ...)
- Validate view: legacy CSV does not raise "Invalid template headers"
- Import view: cached legacy payload runs LegacyImporter and persists rows
"""
from __future__ import annotations

import textwrap

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "bulk-upload-legacy-tests",
    }
}

from accounts.models import User
from admin_panel.auth.models import AdminUser
from admin_panel.bulk_upload.legacy_runner import (
    cache_legacy_payload,
    get_cached_legacy_payload,
    validate_legacy_csv_text,
)
from admin_panel.bulk_upload.models import BulkUploadJob
from admin_panel.bulk_upload.parser import is_legacy_format


LEGACY_CSV = textwrap.dedent(
    """\
    Name, Phone Number, Email, Date Of Birth, Gender, Partner Preference, Country, State, District, City, Address, Religion, Caste, Mother Toungue, Marital Status, Has Children, Number Of Children, Height (cm), Weight (kg), Complexion, Highest Education, Education Subject, Employment, Occupation, Annual Income, About Me, Family Type, Father's Name, Father's Occupation, Mother's Name, Mother's Occupation, Family Status, Number of Brothers, Number Of Married Brothers, Number of Sisters, Number of Married Sisters, About My Family, horochart, amsachart, bhavchart, sishta_dur, star, padam
    SOBHANA.G.K, 8157012545 W, , 11/03/1962, F, No Info, INDIA, KERALA, ALAPPUZHA, THURAVOOR, KAITHA NIKARTHCHERTHALA, Hindu, PULAYYA, Malayalam, Second Marriage, No Info, No Info, 156, No Info, White, Diploma, ALL, RTD NURSE, , 0, No Info, No Info, KUNJU MON, , MOTHER, HOUSE WIFE, No Info, 3, 3, 0, 2, No Info, HKAKKKLJDJH, HBHHGGFBJDI, HKAKJKLJDJH, 224, Bharani, 4
    SUDHEESH, 8129450610, , 10/02/1983, M, No Info, INDIA, KERALA, ALAPPUZHA, CHERTHALA, VATTAPARAMBILC M C 18, Hindu, PATTARYA, Malayalam, Second Marriage, No Info, No Info, 168, No Info, Fair, Graduation, ALL, ACCOUNTS STAFF, ASWATHY PETROL PUMB, 0, No Info, No Info, THANKAPPANPILLA, , SANTHAMMA, HOUSE WIFE, No Info, 2, 2, 0, 1, No Info, GJJKJHKGCII, JFJBJHAJICC, GKJLJHKGCII, 1148, Karthika, 2
    """
)


class LegacyFormatDetectionTests(TestCase):
    def test_detects_legacy_fingerprints(self):
        legacy_headers = [
            "name",
            "phone number",
            "mother toungue",
            "horochart",
            "padam",
        ]
        modern_headers = [
            "name",
            "phone number",
            "mother tongue",
            "marital status",
        ]
        self.assertTrue(is_legacy_format(legacy_headers))
        self.assertFalse(is_legacy_format(modern_headers))


@override_settings(CACHES=LOCMEM_CACHES)
class LegacyRunnerTests(TestCase):
    def test_validate_returns_per_row_results(self):
        result = validate_legacy_csv_text(LEGACY_CSV)
        self.assertEqual(result["total_rows"], 2)
        self.assertEqual(result["valid_rows"], 2)
        self.assertEqual(result["error_rows"], 0)
        self.assertEqual(result["errors"], [])

    def test_cache_roundtrip(self):
        token = cache_legacy_payload({"admin_user_id": 1, "job_id": 99, "csv_text": "x"})
        self.assertEqual(get_cached_legacy_payload(token)["job_id"], 99)


@override_settings(CACHES=LOCMEM_CACHES)
class LegacyBulkUploadEndToEndTests(TestCase):
    def setUp(self):
        self.admin = AdminUser.objects.create(
            mobile="+919876543210",
            role=AdminUser.ROLE_ADMIN,
            name="Test Admin",
            is_active=True,
        )
        self.client = APIClient()
        # Bypass admin JWT by setting request.user via force_authenticate.
        self.client.force_authenticate(user=self.admin)

    def _validate(self, csv_bytes: bytes):
        upload = SimpleUploadedFile("legacy.csv", csv_bytes, content_type="text/csv")
        return self.client.post(reverse("bulk-upload-validate"), {"file": upload}, format="multipart")

    def test_validate_accepts_legacy_csv(self):
        resp = self._validate(LEGACY_CSV.encode("utf-8"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["data"]["legacy"])
        self.assertEqual(body["data"]["total_rows"], 2)
        self.assertEqual(body["data"]["valid_rows"], 2)

    def test_import_persists_legacy_rows(self):
        validate_resp = self._validate(LEGACY_CSV.encode("utf-8"))
        token = validate_resp.json()["data"]["validation_token"]

        import_resp = self.client.post(
            reverse("bulk-upload-import"),
            {"validation_token": token},
            format="json",
        )
        self.assertEqual(import_resp.status_code, 200)
        body = import_resp.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["data"]["legacy"])
        self.assertEqual(body["data"]["imported"], 2)

        self.assertTrue(User.objects.filter(mobile="8157012545").exists())
        self.assertTrue(User.objects.filter(mobile="8129450610").exists())

        job = BulkUploadJob.objects.get(pk=body["data"]["job_id"])
        self.assertEqual(job.status, BulkUploadJob.STATUS_COMPLETED)
        self.assertEqual(job.imported_count, 2)
