import os
import unittest
from datetime import date

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'matrimony_backend.settings')
django.setup()

from astrology.services.horoscope_service import _vedic_weekday


class VedicWeekdayTests(unittest.TestCase):
    def test_sunday_is_zero(self):
        # 2023-01-01 is Sunday (Python weekday 6)
        self.assertEqual(_vedic_weekday(date(2023, 1, 1)), 0)

    def test_monday_is_one(self):
        # 2023-01-02 is Monday
        self.assertEqual(_vedic_weekday(date(2023, 1, 2)), 1)


if __name__ == '__main__':
    unittest.main()
