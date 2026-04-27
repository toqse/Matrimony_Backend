import unittest
from datetime import date, time
from unittest.mock import patch


class GulikaPayloadTests(unittest.TestCase):
    def test_generate_payload_contains_gulika_shape(self):
        try:
            from astrology.services import horoscope_service as hs
        except Exception as exc:  # pragma: no cover
            self.skipTest(f'horoscope_service import failed: {exc}')

        if getattr(hs, 'swe', None) is None:  # pragma: no cover
            self.skipTest('pyswisseph not installed in this environment')

        with patch.object(hs, '_geocode_place', return_value=(9.9312, 76.2673)):
            payload = hs.generate_horoscope_payload(
                date(1994, 1, 15),
                time(9, 30, 0),
                'Kochi, Kerala, India',
            )

        planets = ((payload.get('grahanila') or {}).get('planets') or {})
        self.assertIn('gulika', planets)
        gulika = planets.get('gulika') or {}
        self.assertEqual(gulika.get('full_name'), 'Gulika')
        self.assertEqual(gulika.get('short_name'), 'Gu')
        self.assertIsNotNone(gulika.get('rasi'))
        glon = float(gulika.get('longitude'))
        self.assertGreaterEqual(glon, 0.0)
        self.assertLess(glon, 360.0)


if __name__ == '__main__':
    unittest.main()
