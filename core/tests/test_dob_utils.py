"""Tests for registration DOB parsing and age rules."""
from datetime import date
import unittest

from core.dob_utils import (
    calculate_age,
    parse_registration_dob_string,
    validate_matrimony_registration_dob,
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


class ValidateMatrimonyRegistrationDobTests(unittest.TestCase):
    def test_future(self):
        with self.assertRaises(ValueError) as ctx:
            validate_matrimony_registration_dob(
                date(2030, 1, 1), "M", today=date(2025, 1, 1)
            )
        self.assertEqual(str(ctx.exception), "DOB cannot be in the future")

    def test_unrealistic(self):
        with self.assertRaises(ValueError) as ctx:
            validate_matrimony_registration_dob(
                date(1910, 1, 1), "M", today=date(2025, 1, 1)
            )
        self.assertEqual(str(ctx.exception), "Date of birth is not realistic.")

    def test_male_min_age(self):
        with self.assertRaises(ValueError) as ctx:
            validate_matrimony_registration_dob(
                date(2005, 6, 15), "M", today=date(2025, 6, 15)
            )
        self.assertEqual(str(ctx.exception), "Minimum age for male is 21 years")

    def test_female_min_age(self):
        with self.assertRaises(ValueError) as ctx:
            validate_matrimony_registration_dob(
                date(2010, 6, 15), "F", today=date(2025, 6, 15)
            )
        self.assertEqual(str(ctx.exception), "Minimum age for female is 18 years")

    def test_max_age(self):
        with self.assertRaises(ValueError) as ctx:
            validate_matrimony_registration_dob(
                date(1920, 1, 1), "F", today=date(2025, 1, 1)
            )
        self.assertEqual(str(ctx.exception), "Maximum age allowed is 80 years")

    def test_male_21_ok(self):
        validate_matrimony_registration_dob(
            date(2004, 6, 15), "M", today=date(2025, 6, 15)
        )

    def test_female_18_ok(self):
        validate_matrimony_registration_dob(
            date(2007, 6, 15), "F", today=date(2025, 6, 15)
        )


if __name__ == "__main__":
    unittest.main()
