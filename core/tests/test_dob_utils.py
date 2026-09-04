"""Tests for registration DOB parsing and age rules."""
from datetime import date
import unittest

from core.dob_utils import (
    PROFILE_AGE_ERROR,
    calculate_age,
    parse_registration_dob_string,
    validate_matrimony_registration_dob,
    validate_profile_age,
)


class CalculateAgeTests(unittest.TestCase):
    def test_birthday_not_yet_this_year(self):
        self.assertEqual(
            calculate_age(date(2000, 6, 15), today=date(2025, 3, 1)),
            24,
        )

    def test_birthday_passed_this_year(self):
        self.assertEqual(
            calculate_age(date(2000, 3, 1), today=date(2025, 6, 15)),
            25,
        )

    def test_birthday_today(self):
        self.assertEqual(
            calculate_age(date(2000, 3, 26), today=date(2025, 3, 26)),
            25,
        )


class ParseRegistrationDobTests(unittest.TestCase):
    def test_dash_format(self):
        self.assertEqual(
            parse_registration_dob_string("16-12-1990"),
            date(1990, 12, 16),
        )

    def test_slash_format(self):
        self.assertEqual(
            parse_registration_dob_string("16/12/1990"),
            date(1990, 12, 16),
        )

    def test_leap_day(self):
        self.assertEqual(
            parse_registration_dob_string("29-02-2020"),
            date(2020, 2, 29),
        )

    def test_invalid_leap_day(self):
        with self.assertRaises(ValueError):
            parse_registration_dob_string("29-02-2019")

    def test_invalid_calendar_day(self):
        with self.assertRaises(ValueError) as ctx:
            parse_registration_dob_string("31-02-2020")
        self.assertIn("Invalid date", str(ctx.exception))

    def test_mixed_separators(self):
        with self.assertRaises(ValueError) as ctx:
            parse_registration_dob_string("16-12/1990")
        self.assertIn("Invalid date format", str(ctx.exception))

    def test_iso_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            parse_registration_dob_string("1990-12-16")
        self.assertIn("Invalid date format", str(ctx.exception))


class ValidateProfileAgeTests(unittest.TestCase):
    def test_future(self):
        with self.assertRaises(ValueError) as ctx:
            validate_profile_age(date(2030, 1, 1), today=date(2025, 1, 1))
        self.assertEqual(str(ctx.exception), "DOB cannot be in the future")

    def test_unrealistic(self):
        with self.assertRaises(ValueError) as ctx:
            validate_profile_age(date(1910, 1, 1), today=date(2025, 1, 1))
        self.assertEqual(str(ctx.exception), "Date of birth is not realistic.")

    def test_age_17_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_profile_age(date(2008, 1, 1), today=date(2025, 1, 1))
        self.assertEqual(str(ctx.exception), PROFILE_AGE_ERROR)

    def test_age_18_ok(self):
        validate_profile_age(date(2007, 1, 1), today=date(2025, 1, 1))

    def test_dob_17_06_2008_ok_on_2026_09_04(self):
        validate_profile_age(date(2008, 6, 17), today=date(2026, 9, 4))

    def test_age_19_ok_all_genders(self):
        dob = date(2006, 1, 1)
        today = date(2025, 1, 1)
        validate_profile_age(dob, today=today)
        for gender in ("M", "F", "O"):
            validate_matrimony_registration_dob(dob, gender, today=today)

    def test_age_79_ok(self):
        validate_profile_age(date(1946, 1, 1), today=date(2025, 1, 1))

    def test_age_80_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_profile_age(date(1945, 1, 1), today=date(2025, 1, 1))
        self.assertEqual(str(ctx.exception), PROFILE_AGE_ERROR)

    def test_male_under_21_now_ok_if_at_least_18(self):
        # Previously male min was 21; unified rule allows 18+.
        validate_matrimony_registration_dob(
            date(2005, 6, 15), "M", today=date(2025, 6, 15)
        )


if __name__ == "__main__":
    unittest.main()
