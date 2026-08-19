"""Tests for the legacy CSV import package and management command.

Covers the noisy edges from the source export: phones with stray characters,
slash-formatted DOBs, `No Info` placeholders, parent-name placeholders,
horoscope star aliases, and end-to-end import + skip-existing behaviour.
"""
from __future__ import annotations

import csv
import io
import textwrap
from pathlib import Path
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from accounts.models import User
from astrology.models import HoroscopeProfile
from master.models import Religion
from profiles.legacy_import import LegacyImporter, parse_legacy_csv, read_legacy_csv_text
from profiles.legacy_import.geocode import PlaceGeocoder, place_of_birth_from_row
from profiles.legacy_import.horoscope import resolve_padam, resolve_star, star_lookup
from profiles.models import UserProfile
from profiles.legacy_import.masters import (
    normalize_complexion_name,
    normalize_religion_name,
)
from profiles.legacy_import.normalize import (
    clean,
    parent_name,
    parse_dob,
    parse_email,
    parse_gender,
    parse_int,
    parse_phone,
    parse_tob,
    time_of_birth_from_row,
)


SAMPLE_CSV = textwrap.dedent(
    """\
    Name, Phone Number, Email, Date Of Birth, Gender, Partner Preference, Country, State, District, City, Address, Religion, Caste, Mother Toungue, Marital Status, Has Children, Number Of Children, Height (cm), Weight (kg), Complexion, Highest Education, Education Subject, Employment, Occupation, Annual Income, About Me, Family Type, Father's Name, Father's Occupation, Mother's Name, Mother's Occupation, Family Status, Number of Brothers, Number Of Married Brothers, Number of Sisters, Number of Married Sisters, About My Family, horochart, amsachart, bhavchart, sishta_dur, star, padam
    SOBHANA.G.K, 8157012545 W, , 11/03/1962, F, No Info, INDIA, KERALA, ALAPPUZHA, THURAVOOR, KAITHA NIKARTHCHERTHALA, Hindu, PULAYYA, Malayalam, Second Marriage, No Info, No Info, 156, No Info, White, Diploma, ALL, RTD NURSE, , 0, No Info, No Info, KUNJU MON, , MOTHER, HOUSE WIFE, No Info, 3, 3, 0, 2, No Info, HKAKKKLJDJH, HBHHGGFBJDI, HKAKJKLJDJH, 224, Bharani, 4
    M, No Info, INDIA, KERALA, ALAPPUZHA, , , Hindu, , Malayalam, Second Marriage, No Info, No Info, 0, No Info, , , ALL, , , 0, No Info, No Info, , , , , No Info, 0, 0, 0, 0, No Info, , , , 0, , 0
    """
)


class NormalizeTests(SimpleTestCase):
    """Unit tests for the cell-level helpers in legacy_import.normalize."""

    def test_parse_phone_keeps_first_valid_mobile(self):
        self.assertEqual(parse_phone("8157012545 W"), "8157012545")
        self.assertEqual(parse_phone("9400719881 W8547948024"), "9400719881")
        self.assertEqual(parse_phone("8281439947W"), "8281439947")
        self.assertEqual(parse_phone(" 91 9876543210 "), "9876543210")

    def test_parse_phone_ignores_landline_or_blank(self):
        self.assertIsNone(parse_phone("RES 04822 237124"))
        self.assertIsNone(parse_phone(""))
        self.assertIsNone(parse_phone(None))

    def test_parse_dob_accepts_legacy_slash_format(self):
        self.assertEqual(parse_dob("11/03/1962").isoformat(), "1962-03-11")
        self.assertEqual(parse_dob("11-03-1962").isoformat(), "1962-03-11")
        self.assertIsNone(parse_dob("No Info"))
        self.assertIsNone(parse_dob("not-a-date"))

    def test_clean_strips_no_info(self):
        self.assertEqual(clean(" No Info "), "")
        self.assertEqual(clean("  SOBHANA.G.K "), "SOBHANA.G.K")
        self.assertEqual(clean("0", zero_is_blank=True), "")
        self.assertEqual(clean("0"), "0")

    def test_parse_int_clamps_negative_and_blank(self):
        self.assertEqual(parse_int("-1"), 0)
        self.assertEqual(parse_int("3"), 3)
        self.assertEqual(parse_int(""), 0)
        self.assertEqual(parse_int("No Info"), 0)

    def test_parse_email_validates(self):
        self.assertEqual(parse_email("foo@bar.com"), "foo@bar.com")
        self.assertIsNone(parse_email("not-an-email"))
        self.assertIsNone(parse_email(""))

    def test_parse_gender_normalizes_words(self):
        self.assertEqual(parse_gender("male"), "M")
        self.assertEqual(parse_gender("F"), "F")
        self.assertEqual(parse_gender("other"), "O")
        self.assertEqual(parse_gender("?"), "")

    def test_parent_name_drops_placeholders(self):
        self.assertEqual(parent_name("FATHER"), "")
        self.assertEqual(parent_name("Mother"), "")
        self.assertEqual(parent_name("KUNJU MON"), "KUNJU MON")

    def test_parse_tob_accepts_common_formats(self):
        self.assertEqual(parse_tob("14:30").isoformat(), "14:30:00")
        self.assertEqual(parse_tob("9:05").isoformat(), "09:05:00")
        self.assertEqual(parse_tob("09:05:00").isoformat(), "09:05:00")
        self.assertIsNone(parse_tob(""))
        self.assertIsNone(parse_tob("No Info"))
        self.assertIsNone(parse_tob("not-a-time"))

    def test_time_of_birth_from_row_aliases(self):
        self.assertEqual(
            time_of_birth_from_row({"time of birth": "14:30"}).isoformat(),
            "14:30:00",
        )
        self.assertEqual(
            time_of_birth_from_row({"birth time": "9:05"}).isoformat(),
            "09:05:00",
        )
        self.assertIsNone(time_of_birth_from_row({}))


class StarLookupTests(SimpleTestCase):
    """Unit tests for horoscope star/padam mapping."""

    def test_star_lookup_supports_canonical_names(self):
        stars = star_lookup()
        self.assertEqual(stars["bharani"], 2)
        self.assertEqual(stars["anizham"], 17)

    def test_star_lookup_supports_legacy_aliases(self):
        stars = star_lookup()
        self.assertEqual(stars["makayeeram"], 5)
        self.assertEqual(stars["chithira"], 14)
        self.assertEqual(stars["avittom"], 23)
        self.assertEqual(stars["chathayom"], 24)
        self.assertEqual(stars["uthrittathi"], 26)

    def test_resolve_star_returns_warning_for_unknown(self):
        stars = star_lookup()
        number, warning = resolve_star("Bharani", stars)
        self.assertEqual((number, warning), (2, ""))
        number, warning = resolve_star("Bogus", stars)
        self.assertIsNone(number)
        self.assertEqual(warning, "Bogus")
        number, warning = resolve_star("No Info", stars)
        self.assertIsNone(number)
        self.assertEqual(warning, "")

    def test_resolve_padam_clamps_out_of_range(self):
        self.assertEqual(resolve_padam("3"), 3)
        self.assertIsNone(resolve_padam("0"))
        self.assertIsNone(resolve_padam("9"))


class MasterAliasTests(SimpleTestCase):
    """Religion and complexion alias normalization."""

    def test_religion_alias(self):
        self.assertEqual(normalize_religion_name("Hindu"), "Hinduism")
        self.assertEqual(normalize_religion_name("Christian"), "Christianity")
        self.assertEqual(normalize_religion_name("ROMAN CATHLIC"), "ROMAN CATHLIC")

    def test_complexion_alias(self):
        self.assertEqual(normalize_complexion_name("White"), "Very Fair")
        self.assertEqual(normalize_complexion_name("Medium"), "Wheatish")
        self.assertEqual(normalize_complexion_name("Medium White"), "Wheatish")


class ParserTests(SimpleTestCase):
    """CSV-level header validation."""

    def test_parse_legacy_csv_validates_headers(self):
        headers, reader = parse_legacy_csv(SAMPLE_CSV)
        self.assertEqual(headers[0], "name")
        self.assertEqual(headers[-1], "padam")
        rows = list(reader)
        self.assertGreaterEqual(len(rows), 1)

    def test_parse_legacy_csv_rejects_unknown_headers(self):
        bad = "Foo,Bar\n1,2\n"
        with self.assertRaises(ValueError):
            parse_legacy_csv(bad)

    def test_parse_legacy_csv_accepts_optional_pob_column(self):
        with_pob = SAMPLE_CSV.replace(
            "star, padam\n",
            "star, padam, Place of Birth\n",
        ).replace(
            "Bharani, 4\n",
            "Bharani, 4, Madurai Tamil Nadu India\n",
        )
        headers, reader = parse_legacy_csv(with_pob)
        self.assertEqual(headers[-1], "place of birth")
        rows = list(reader)
        self.assertEqual(rows[0]["place of birth"].strip(), "Madurai Tamil Nadu India")

    def test_parse_legacy_csv_accepts_optional_pob_and_tob_columns(self):
        with_pob_tob = SAMPLE_CSV.replace(
            "star, padam\n",
            "star, padam, Place of Birth, Time of Birth\n",
        ).replace(
            "Bharani, 4\n",
            "Bharani, 4, Madurai Tamil Nadu India, 14:30\n",
        )
        headers, reader = parse_legacy_csv(with_pob_tob)
        self.assertEqual(headers[-2], "place of birth")
        self.assertEqual(headers[-1], "time of birth")
        rows = list(reader)
        self.assertEqual(rows[0]["place of birth"].strip(), "Madurai Tamil Nadu India")
        self.assertEqual(rows[0]["time of birth"].strip(), "14:30")

    def test_read_legacy_csv_text_falls_back_to_latin1(self, tmp_path=None):
        # Embed a non-UTF-8 byte (0xD1) inline in the file.
        path = Path("legacy_import_latin1_fixture.csv")
        try:
            path.write_bytes(b"Name,Phone Number\nFoo\xd1,1234567890\n")
            text = read_legacy_csv_text(path)
            self.assertIn("\xd1", text)
        finally:
            if path.exists():
                path.unlink()


class LegacyImporterTests(TestCase):
    """End-to-end build_payload + save + skip-existing behaviour."""

    def setUp(self):
        self.row = {
            "name": "  SOBHANA.G.K ",
            "phone number": "8157012545 W",
            "email": "",
            "date of birth": "11/03/1962",
            "gender": "F",
            "partner preference": "No Info",
            "country": "INDIA",
            "state": "KERALA",
            "district": "ALAPPUZHA",
            "city": "THURAVOOR",
            "address": "KAITHA NIKARTHCHERTHALA",
            "religion": "Hindu",
            "caste": "PULAYYA",
            "mother toungue": "Malayalam",
            "marital status": "Second Marriage",
            "has children": "No Info",
            "number of children": "No Info",
            "height (cm)": "156",
            "weight (kg)": "No Info",
            "complexion": "White",
            "highest education": "Diploma",
            "education subject": "ALL",
            "employment": "RTD NURSE",
            "occupation": "",
            "annual income": "0",
            "about me": "No Info",
            "family type": "No Info",
            "father's name": "KUNJU MON",
            "father's occupation": "",
            "mother's name": "MOTHER",
            "mother's occupation": "HOUSE WIFE",
            "family status": "No Info",
            "number of brothers": "3",
            "number of married brothers": "3",
            "number of sisters": "0",
            "number of married sisters": "2",
            "about my family": "No Info",
            "horochart": "HKAKKKLJDJH",
            "amsachart": "HBHHGGFBJDI",
            "bhavchart": "HKAKJKLJDJH",
            "sishta_dur": "224",
            "star": "Bharani",
            "padam": "4",
        }

    def test_place_of_birth_aliases(self):
        self.assertEqual(
            place_of_birth_from_row({"place of birth": "  Madurai  "}),
            "Madurai",
        )
        self.assertEqual(place_of_birth_from_row({"pob": "Kochi"}), "Kochi")
        self.assertEqual(place_of_birth_from_row({"birth place": "Kottayam"}), "Kottayam")
        self.assertEqual(place_of_birth_from_row(self.row), "")

    def test_build_payload_reads_place_of_birth(self):
        importer = LegacyImporter(dry_run=True)
        row = dict(self.row, **{"place of birth": "Madurai, Tamil Nadu, India"})
        payload, reason = importer.build_payload(2, row)
        self.assertEqual(reason, "")
        self.assertEqual(payload["place_of_birth"], "Madurai, Tamil Nadu, India")

    def test_empty_place_of_birth_skips_geocode(self):
        importer = LegacyImporter()
        payload, _ = importer.build_payload(2, self.row)
        with patch.object(importer._geocoder, "resolve") as resolve:
            user = importer.save(payload)
        resolve.assert_not_called()
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.place_of_birth, "")
        self.assertIsNone(profile.birth_latitude)
        self.assertIsNone(profile.birth_longitude)
        hp = HoroscopeProfile.objects.get(user=user)
        self.assertIsNone(hp.pr_lat)
        self.assertIsNone(hp.pr_lon)

    def test_save_geocodes_place_of_birth(self):
        importer = LegacyImporter()
        row = dict(self.row, **{"place of birth": "Madurai, Tamil Nadu, India"})
        payload, _ = importer.build_payload(2, row)
        with patch.object(
            importer._geocoder, "resolve", return_value=(9.9252, 78.1198)
        ) as resolve:
            user = importer.save(payload)
        resolve.assert_called_once_with("Madurai, Tamil Nadu, India")
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.place_of_birth, "Madurai, Tamil Nadu, India")
        self.assertAlmostEqual(profile.birth_latitude, 9.9252)
        self.assertAlmostEqual(profile.birth_longitude, 78.1198)
        hp = HoroscopeProfile.objects.get(user=user)
        self.assertAlmostEqual(hp.pr_lat, 9.9252)
        self.assertAlmostEqual(hp.pr_lon, 78.1198)
        self.assertEqual(hp.pr_rasi, "HKAKKKLJDJH")
        self.assertTrue(hp.is_calculated)

    def test_geocode_failure_keeps_pob_without_coords(self):
        importer = LegacyImporter()
        row = dict(self.row, **{"place of birth": "Unknown Hamlet XYZ"})
        payload, _ = importer.build_payload(2, row)
        with patch.object(importer._geocoder, "resolve", return_value=None):
            user = importer.save(payload)
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.place_of_birth, "Unknown Hamlet XYZ")
        self.assertIsNone(profile.birth_latitude)
        hp = HoroscopeProfile.objects.get(user=user)
        self.assertIsNone(hp.pr_lat)

    def test_build_payload_reads_time_of_birth(self):
        importer = LegacyImporter(dry_run=True)
        row = dict(self.row, **{"time of birth": "14:30"})
        payload, reason = importer.build_payload(2, row)
        self.assertEqual(reason, "")
        self.assertEqual(payload["time_of_birth"].isoformat(), "14:30:00")

    def test_save_persists_time_of_birth(self):
        importer = LegacyImporter()
        row = dict(self.row, **{"time of birth": "14:30"})
        payload, _ = importer.build_payload(2, row)
        user = importer.save(payload)
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.time_of_birth.isoformat(), "14:30:00")
        self.assertEqual(profile.birth_timezone, 5.5)
        hp = HoroscopeProfile.objects.get(user=user)
        self.assertEqual(hp.pr_tob.isoformat(), "14:30:00")

    def test_invalid_time_of_birth_fail_soft(self):
        importer = LegacyImporter()
        row = dict(self.row, **{"time of birth": "not-a-time"})
        payload, _ = importer.build_payload(2, row)
        user = importer.save(payload)
        profile = UserProfile.objects.get(user=user)
        self.assertIsNone(profile.time_of_birth)
        hp = HoroscopeProfile.objects.get(user=user)
        self.assertIsNone(hp.pr_tob)

    def test_save_creates_user_and_horoscope(self):
        importer = LegacyImporter()
        payload, reason = importer.build_payload(2, self.row)
        self.assertEqual(reason, "")
        user = importer.save(payload)
        self.assertIsNotNone(user)
        self.assertEqual(user.mobile, "8157012545")
        self.assertEqual(user.gender, "F")
        self.assertEqual(user.dob.isoformat(), "1962-03-11")
        # 'Hindu' should normalize to a Religion row even if seeded as 'Hinduism'.
        self.assertTrue(Religion.objects.filter(name__iexact="Hinduism").exists())
        # Horoscope chart fields persisted with mapped star number.
        hp = HoroscopeProfile.objects.get(user=user)
        self.assertEqual(hp.pr_rasi, "HKAKKKLJDJH")
        self.assertEqual(hp.pr_star, 2)  # Bharani
        self.assertEqual(hp.pr_pada, 4)
        # Parent-name placeholder dropped.
        self.assertEqual(user.user_family.mother_name, "")
        self.assertEqual(user.user_family.father_name, "KUNJU MON")

    def test_skip_existing_phone(self):
        User.objects.create_user(mobile="8157012545", password="x", role="user")
        importer = LegacyImporter()
        payload, reason = importer.build_payload(2, self.row)
        self.assertIsNone(payload)
        self.assertEqual(reason, "phone_exists_in_db")

    def test_skip_invalid_name_row(self):
        importer = LegacyImporter()
        bad = dict(self.row, name=" M ")
        payload, reason = importer.build_payload(3, bad)
        self.assertIsNone(payload)
        self.assertEqual(reason, "missing_or_invalid_name")

    def test_skip_invalid_gender_row(self):
        importer = LegacyImporter()
        bad = dict(self.row, gender="?")
        payload, reason = importer.build_payload(4, bad)
        self.assertIsNone(payload)
        self.assertEqual(reason, "invalid_gender")

    def test_dry_run_does_not_persist(self):
        importer = LegacyImporter(dry_run=True)
        payload, _ = importer.build_payload(2, self.row)
        result = importer.save(payload)
        self.assertIsNone(result)
        self.assertFalse(User.objects.filter(mobile="8157012545").exists())


class PlaceGeocoderTests(TestCase):
    """Unit tests for Nominatim throttle / cache / fail-soft."""

    def test_empty_place_returns_none(self):
        geo = PlaceGeocoder(nominatim_delay_seconds=0)
        self.assertIsNone(geo.resolve(""))
        self.assertIsNone(geo.resolve("No Info"))

    def test_fallback_skips_nominatim(self):
        geo = PlaceGeocoder(nominatim_delay_seconds=0)
        with patch(
            "astrology.services.horoscope_service._fallback_lat_lon",
            return_value=(9.9312, 76.2673),
        ) as fallback, patch(
            "astrology.services.horoscope_service._geocode_place"
        ) as nominatim:
            coords = geo.resolve("Kochi, Kerala, India")
        self.assertEqual(coords, (9.9312, 76.2673))
        fallback.assert_called_once()
        nominatim.assert_not_called()

    def test_caches_nominatim_and_throttles_once(self):
        geo = PlaceGeocoder(nominatim_delay_seconds=0)
        with patch(
            "astrology.services.horoscope_service._fallback_lat_lon",
            return_value=None,
        ), patch(
            "astrology.services.horoscope_service._geocode_place",
            return_value=(9.9252, 78.1198),
        ) as nominatim:
            first = geo.resolve("Madurai, Tamil Nadu, India")
            second = geo.resolve("madurai, tamil nadu, india")
        self.assertEqual(first, (9.9252, 78.1198))
        self.assertEqual(second, (9.9252, 78.1198))
        nominatim.assert_called_once()

    def test_nominatim_failure_is_soft(self):
        geo = PlaceGeocoder(nominatim_delay_seconds=0)
        with patch(
            "astrology.services.horoscope_service._fallback_lat_lon",
            return_value=None,
        ), patch(
            "astrology.services.horoscope_service._geocode_place",
            side_effect=ValueError("Unable to resolve place_of_birth."),
        ):
            self.assertIsNone(geo.resolve("Not A Real Place 999"))


class ImportLegacyCsvCommandTests(TestCase):
    """Smoke tests for the `import_legacy_csv` management command."""

    def _write_csv(self, path: Path):
        path.write_text(SAMPLE_CSV, encoding="utf-8")

    def test_dry_run_writes_report_without_writing_db(self):
        csv_path = Path("legacy_import_test_input.csv")
        report_path = Path("legacy_import_test_report.csv")
        try:
            self._write_csv(csv_path)
            out = io.StringIO()
            call_command(
                "import_legacy_csv",
                str(csv_path),
                "--dry-run",
                "--report",
                str(report_path),
                stdout=out,
            )
            self.assertIn("Validated", out.getvalue())
            self.assertFalse(User.objects.filter(mobile="8157012545").exists())
            with report_path.open() as f:
                rows = list(csv.DictReader(f))
            statuses = {r["status"] for r in rows}
            self.assertIn("valid", statuses)
            self.assertIn("skipped", statuses)
        finally:
            for p in (csv_path, report_path):
                if p.exists():
                    p.unlink()

    def test_unknown_branch_raises(self):
        csv_path = Path("legacy_import_test_input.csv")
        try:
            self._write_csv(csv_path)
            with self.assertRaises(CommandError):
                call_command(
                    "import_legacy_csv",
                    str(csv_path),
                    "--dry-run",
                    "--branch",
                    "DOES_NOT_EXIST",
                )
        finally:
            if csv_path.exists():
                csv_path.unlink()
