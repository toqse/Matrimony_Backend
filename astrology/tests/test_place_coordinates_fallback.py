"""Stable Kerala place coordinates vs Nominatim variance."""
import os
import unittest

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'matrimony_backend.settings')
django.setup()

from astrology.services.horoscope_service import _fallback_lat_lon


class KeralaPlaceFallbackTests(unittest.TestCase):
    def test_ernakulam_resolves(self):
        lat, lon = _fallback_lat_lon('Ernakulam, Kerala')
        self.assertAlmostEqual(lat, 9.9816, places=3)
        self.assertAlmostEqual(lon, 76.267304, places=3)

    def test_alappuzha_resolves(self):
        lat, lon = _fallback_lat_lon('Alappuzha')
        self.assertAlmostEqual(lat, 9.4981, places=3)
        self.assertAlmostEqual(lon, 76.338848, places=3)
