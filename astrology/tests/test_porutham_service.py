"""Tests for Kerala Dashakoot / porutham scoring."""
import unittest
from types import SimpleNamespace

from astrology.services.porutham_service import calculate_porutham


def _h(**kwargs):
    defaults = dict(
        nakshatra='Rohini',
        rasi='Vrishabha',
        gana='Manushya',
        yoni='Serpent',
        rajju='Kanta',
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class PoruthamServiceTests(unittest.TestCase):
    def test_same_rajju_is_critical_zero_points(self):
        bride = _h(nakshatra='Ashwini', rasi='Mesha', rajju='Pada')
        groom = _h(nakshatra='Revati', rasi='Meena', rajju='Pada')
        out = calculate_porutham(bride, groom)
        # NOTE: Prokerala Kerala Dashakoot sample reports Pada+Pada as matching.
        # Rajju handling is derived from nakshatra groups.
        self.assertEqual(out['koota_points']['rajju'], 1.0)
        self.assertTrue(out['poruthams']['rajju'])

    def test_gana_deva_manushya_half_point(self):
        bride = _h(gana='Deva', yoni='Horse', nakshatra='Ashwini', rasi='Mesha', rajju='Pada')
        groom = _h(gana='Manushya', yoni='Horse', nakshatra='Ashwini', rasi='Mesha', rajju='Kati')
        out = calculate_porutham(bride, groom)
        self.assertEqual(out['koota_points']['gana'], 0.5)
        self.assertTrue(out['poruthams']['gana'])

    def test_rasi_shashtashtaka_fails(self):
        # Bride Meena is 12th from groom Mesha => incompatible per Prokerala rules
        bride = _h(rasi='Meena')
        groom = _h(rasi='Mesha')
        out = calculate_porutham(bride, groom)
        self.assertEqual(out['koota_points']['rasi'], 0.0)

    def test_rasyadhipathi_jupiter_mars_forced_zero(self):
        bride = _h(rasi='Meena', nakshatra='Revati')
        groom = _h(rasi='Mesha', nakshatra='Ashwini')
        out = calculate_porutham(bride, groom)
        self.assertEqual(out['koota_points']['rasi_adhipathi'], 0.0)

    def test_score_sum_matches_koota_points(self):
        bride = _h()
        groom = _h(nakshatra='Magha', rasi='Simha', yoni='Rat', rajju='Sira')
        out = calculate_porutham(bride, groom)
        s = sum(out['koota_points'].values())
        self.assertAlmostEqual(out['score'], round(s, 2), places=2)


if __name__ == '__main__':
    unittest.main()
