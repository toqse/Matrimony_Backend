"""Kuja dosham: Lagna chart and Chandra lagna chart (moon-based whole-sign houses)."""

import unittest
from types import SimpleNamespace

from astrology.services.generate_ui_service import kuja_dosham_horoscope


class KujaDoshamChandraTests(unittest.TestCase):
    def test_mars_clear_from_lagna_but_seventh_from_moon_is_kuja(self):
        # Synthetic longitudes (whole-sign indices): Mangal seventh from Moon, not Mangal-house from Lagna alone.
        # Lagna ~Mesha start; Mars in Simha-ish (house 6 from Mesha → not Kuja-from-Lagna classic set);
        # Moon in Meena; Mars still placed so it is seventh from Moon.
        grahanila = {
            'lagna_longitude': 0.0,
            'planets': {
                'moon': {'longitude': 330.0},
                'mars': {'longitude': 165.0},
            },
        }
        horo = SimpleNamespace(grahanila=grahanila)
        self.assertTrue(kuja_dosham_horoscope(horo))

    def test_mars_only_from_lagna_still_detected_when_moon_absent_longitude(self):
        grahanila = {
            'lagna_longitude': 0.0,
            'planets': {
                'moon': {},  # no longitude → skip Moon check
                'mars': {'longitude': 0.0},
            },
        }
        horo = SimpleNamespace(grahanila=grahanila)
        self.assertTrue(kuja_dosham_horoscope(horo))


if __name__ == '__main__':
    unittest.main()
