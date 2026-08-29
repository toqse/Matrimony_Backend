"""Tests for the legacy-format bulk upload flow.

Covers:
- Header detection: legacy fingerprints (`mother toungue`, `horochart`, ...)
- Validate view: legacy CSV does not raise "Invalid template headers"
- Import view: cached legacy payload runs LegacyImporter and persists rows
"""
from __future__ import annotations

import textwrap
from unittest.mock import patch

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
from admin_panel.bulk_upload.template_assets import (
    get_legacy_template_columns,
    load_legacy_import_template_csv,
)
from astrology.models import HoroscopeProfile
from profiles.models import UserProfile


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
class LegacyTemplateDownloadTests(TestCase):
    def setUp(self):
        self.admin = AdminUser.objects.create(
            mobile="+919876543211",
            role=AdminUser.ROLE_ADMIN,
            name="Template Admin",
            is_active=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_template_columns_endpoint(self):
        resp = self.client.get(reverse("bulk-upload-template"), {"columns": "1"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        columns = body["data"]["columns"]
        self.assertIn("Mother Toungue", columns)
        self.assertIn("Place of Birth", columns)
        self.assertIn("Time of Birth", columns)
        self.assertIn("reg_no", columns)
        self.assertEqual(columns[-2], "Time of Birth")
        self.assertEqual(columns[-1], "reg_no")
        self.assertEqual(len(columns), 46)

    def test_template_csv_download_has_legacy_headers(self):
        resp = self.client.get(
            reverse("bulk-upload-template"),
            {"file_format": "csv"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("matrimony_import_template.csv", resp["Content-Disposition"])
        first_line = resp.content.decode("utf-8-sig").splitlines()[0]
        self.assertIn("Mother Toungue", first_line)
        self.assertIn("Place of Birth", first_line)
        self.assertIn("Time of Birth", first_line)
        self.assertIn("reg_no", first_line)
        self.assertTrue(first_line.rstrip().endswith("reg_no"))

    def test_get_legacy_template_columns_matches_file(self):
        columns = get_legacy_template_columns()
        content, _ = load_legacy_import_template_csv()
        first_line = content.decode("utf-8-sig").splitlines()[0]
        self.assertEqual(columns[0], first_line.split(",")[0])


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
        profile = UserProfile.objects.get(user__mobile="8157012545")
        self.assertEqual(profile.place_of_birth, "")
        self.assertIsNone(profile.birth_latitude)

    def test_validate_accepts_optional_pob_column(self):
        csv_text = LEGACY_CSV.replace(
            "star, padam\n",
            "star, padam, Place of Birth\n",
        ).replace(
            "Bharani, 4\n",
            "Bharani, 4, Madurai Tamil Nadu India\n",
        ).replace(
            "Karthika, 2\n",
            "Karthika, 2,\n",
        )
        resp = self._validate(csv_text.encode("utf-8"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["valid_rows"], 2)

    def test_import_geocodes_place_of_birth(self):
        csv_text = LEGACY_CSV.replace(
            "star, padam\n",
            "star, padam, Place of Birth\n",
        ).replace(
            "Bharani, 4\n",
            "Bharani, 4, Madurai Tamil Nadu India\n",
        ).replace(
            "Karthika, 2\n",
            "Karthika, 2,\n",
        )
        validate_resp = self._validate(csv_text.encode("utf-8"))
        token = validate_resp.json()["data"]["validation_token"]

        with patch(
            "profiles.legacy_import.geocode.PlaceGeocoder.resolve",
            side_effect=lambda place: (9.9252, 78.1198) if place else None,
        ):
            import_resp = self.client.post(
                reverse("bulk-upload-import"),
                {"validation_token": token},
                format="json",
            )
        self.assertEqual(import_resp.status_code, 200)
        self.assertEqual(import_resp.json()["data"]["imported"], 2)

        sobhana = User.objects.get(mobile="8157012545")
        profile = UserProfile.objects.get(user=sobhana)
        self.assertEqual(profile.place_of_birth, "Madurai Tamil Nadu India")
        self.assertAlmostEqual(profile.birth_latitude, 9.9252)
        self.assertAlmostEqual(profile.birth_longitude, 78.1198)
        hp = HoroscopeProfile.objects.get(user=sobhana)
        self.assertAlmostEqual(hp.pr_lat, 9.9252)
        self.assertAlmostEqual(hp.pr_lon, 78.1198)

        sudheesh = User.objects.get(mobile="8129450610")
        empty = UserProfile.objects.get(user=sudheesh)
        self.assertEqual(empty.place_of_birth, "")
        self.assertIsNone(empty.birth_latitude)

    def test_validate_accepts_optional_pob_and_tob_columns(self):
        csv_text = LEGACY_CSV.replace(
            "star, padam\n",
            "star, padam, Place of Birth, Time of Birth\n",
        ).replace(
            "Bharani, 4\n",
            "Bharani, 4, Madurai Tamil Nadu India, 14:30\n",
        ).replace(
            "Karthika, 2\n",
            "Karthika, 2,,\n",
        )
        resp = self._validate(csv_text.encode("utf-8"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["valid_rows"], 2)

    def test_import_persists_time_of_birth(self):
        csv_text = LEGACY_CSV.replace(
            "star, padam\n",
            "star, padam, Place of Birth, Time of Birth\n",
        ).replace(
            "Bharani, 4\n",
            "Bharani, 4, Madurai Tamil Nadu India, 14:30\n",
        ).replace(
            "Karthika, 2\n",
            "Karthika, 2,,\n",
        )
        validate_resp = self._validate(csv_text.encode("utf-8"))
        token = validate_resp.json()["data"]["validation_token"]

        with patch(
            "profiles.legacy_import.geocode.PlaceGeocoder.resolve",
            side_effect=lambda place: (9.9252, 78.1198) if place else None,
        ):
            import_resp = self.client.post(
                reverse("bulk-upload-import"),
                {"validation_token": token},
                format="json",
            )
        self.assertEqual(import_resp.status_code, 200)
        self.assertEqual(import_resp.json()["data"]["imported"], 2)

        sobhana = User.objects.get(mobile="8157012545")
        profile = UserProfile.objects.get(user=sobhana)
        self.assertEqual(profile.time_of_birth.isoformat(), "14:30:00")
        hp = HoroscopeProfile.objects.get(user=sobhana)
        self.assertEqual(hp.pr_tob.isoformat(), "14:30:00")
        self.assertAlmostEqual(hp.pr_lat, 9.9252)

    def test_validate_accepts_optional_reg_no_column(self):
        csv_text = LEGACY_CSV.replace(
            "star, padam\n",
            "star, padam, Place of Birth, Time of Birth, reg_no\n",
        ).replace(
            "Bharani, 4\n",
            "Bharani, 4, Madurai Tamil Nadu India, 14:30, 10038V\n",
        ).replace(
            "Karthika, 2\n",
            "Karthika, 2,,,\n",
        )
        resp = self._validate(csv_text.encode("utf-8"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["valid_rows"], 2)

    def test_import_persists_reg_no(self):
        csv_text = LEGACY_CSV.replace(
            "star, padam\n",
            "star, padam, Place of Birth, Time of Birth, reg_no\n",
        ).replace(
            "Bharani, 4\n",
            "Bharani, 4, Madurai Tamil Nadu India, 14:30, 10038V\n",
        ).replace(
            "Karthika, 2\n",
            "Karthika, 2,,,\n",
        )
        validate_resp = self._validate(csv_text.encode("utf-8"))
        token = validate_resp.json()["data"]["validation_token"]

        import_resp = self.client.post(
            reverse("bulk-upload-import"),
            {"validation_token": token},
            format="json",
        )
        self.assertEqual(import_resp.status_code, 200)
        self.assertEqual(import_resp.json()["data"]["imported"], 2)

        sobhana = User.objects.get(mobile="8157012545")
        self.assertEqual(sobhana.reg_no, "10038V")
        sudheesh = User.objects.get(mobile="8129450610")
        self.assertEqual(sudheesh.reg_no, "")
