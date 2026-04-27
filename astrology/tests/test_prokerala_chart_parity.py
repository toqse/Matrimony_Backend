import unittest
from datetime import date, time
from unittest.mock import patch


class ProkeralaChartParityTests(unittest.TestCase):
    def test_sample_inputs_match_prokerala_rasi_nakshatra(self):
        """
        Prokerala sample (Kerala Dashakoot):
        - Girl: 2003-06-23 01:45 AM, Alappuzha, Kerala, India -> Rasi Meena, Nakshatra Revati
        - Boy : 2001-05-20 12:40 PM, Idukki, Kerala, India    -> Rasi Mesha, Nakshatra Ashwini
        """
        try:
            from astrology.services import horoscope_service as hs
        except Exception as exc:  # pragma: no cover
            self.skipTest(f'horoscope_service import failed: {exc}')

        if getattr(hs, 'swe', None) is None:  # pragma: no cover
            self.skipTest('pyswisseph not installed in this environment')

        # Mock geocode to avoid network / Nominatim dependency.
        def fake_geocode(place: str):
            p = place.lower()
            if 'alappuzha' in p:
                return 9.5003416, 76.4123364
            if 'idukki' in p:
                return 9.8154785, 76.9991599
            return 10.0, 76.0

        with patch.object(hs, '_geocode_place', side_effect=fake_geocode):
            girl = hs.generate_horoscope_payload(
                date(2003, 6, 23),
                time(1, 45, 0),
                'Alappuzha, Kerala, India',
            )
            boy = hs.generate_horoscope_payload(
                date(2001, 5, 20),
                time(12, 40, 0),
                'Idukki, Kerala, India',
            )

        self.assertEqual(girl['rasi'], 'Meena')
        self.assertEqual(girl['nakshatra'], 'Revati')
        self.assertEqual(boy['rasi'], 'Mesha')
        self.assertEqual(boy['nakshatra'], 'Ashwini')
        for payload in (girl, boy):
            planets = ((payload.get('grahanila') or {}).get('planets') or {})
            self.assertIn('gulika', planets)
            gulika = planets.get('gulika') or {}
            self.assertIn('longitude', gulika)
            glon = float(gulika['longitude'])
            self.assertGreaterEqual(glon, 0.0)
            self.assertLess(glon, 360.0)


if __name__ == '__main__':
    unittest.main()

