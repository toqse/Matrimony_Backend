import unittest
from types import SimpleNamespace

from astrology.services import horoscope_service as hs


class AstrologyBirthTimezoneTests(unittest.TestCase):
    def test_birth_timezone_defaults_to_ist(self):
        original_settings = hs.settings
        try:
            hs.settings = SimpleNamespace(ASTROLOGY_BIRTH_TIMEZONE='Asia/Kolkata')
            self.assertEqual(getattr(hs._birth_timezone(), 'key', ''), 'Asia/Kolkata')
        finally:
            hs.settings = original_settings

    def test_birth_timezone_falls_back_for_invalid_value(self):
        original_settings = hs.settings
        try:
            hs.settings = SimpleNamespace(ASTROLOGY_BIRTH_TIMEZONE='Invalid/Timezone')
            self.assertEqual(getattr(hs._birth_timezone(), 'key', ''), 'Asia/Kolkata')
        finally:
            hs.settings = original_settings


if __name__ == '__main__':
    unittest.main()
