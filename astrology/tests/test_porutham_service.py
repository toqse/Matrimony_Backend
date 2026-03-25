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
    def test_sample_revati_ashwini_matches_prokerala(self):
        bride = _h(nakshatra='Revati', rasi='Meena', rajju='Pada')
        groom = _h(nakshatra='Ashwini', rasi='Mesha', rajju='Pada')
        out = calculate_porutham(bride, groom)
        self.assertEqual(out['koota_points']['dina'], 1.0)
        self.assertEqual(out['koota_points']['gana'], 1.0)
        self.assertEqual(out['koota_points']['mahendra'], 0.0)
        self.assertEqual(out['koota_points']['sthree_deergha'], 0.0)
        self.assertEqual(out['koota_points']['yoni'], 1.0)
        self.assertEqual(out['koota_points']['vedha'], 1.0)
        self.assertEqual(out['koota_points']['rajju'], 1.0)
        self.assertEqual(out['koota_points']['rasi'], 0.0)
        self.assertEqual(out['koota_points']['rasi_adhipathi'], 0.0)
        self.assertEqual(out['koota_points']['vasya'], 0.0)
        self.assertEqual(out['score'], 5.0)

    def test_gana_deva_manushya_half_point(self):
        bride = _h(gana='Deva', yoni='Horse', nakshatra='Ashwini', rasi='Mesha', rajju='Pada')
        groom = _h(gana='Manushya', yoni='Rat', nakshatra='Bharani', rasi='Mesha', rajju='Kati')
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

    def test_sample_uttara_bhadrapada_shatabhisha_matches_prokerala(self):
        bride = _h(
            nakshatra='Uttara Bhadrapada',
            rasi='Meena',
            gana='Manushya',
            yoni='Cow',
            rajju='Pada',
        )
        groom = _h(
            nakshatra='Shatabhisha',
            rasi='Kumbha',
            gana='Rakshasa',
            yoni='Horse',
            rajju='Pada',
        )
        out = calculate_porutham(bride, groom)
        self.assertEqual(out['koota_points']['dina'], 1.0)
        self.assertEqual(out['koota_points']['gana'], 0.5)
        self.assertEqual(out['koota_points']['mahendra'], 0.0)
        self.assertEqual(out['koota_points']['sthree_deergha'], 1.0)
        self.assertEqual(out['koota_points']['yoni'], 0.5)
        self.assertEqual(out['koota_points']['vedha'], 1.0)
        self.assertEqual(out['koota_points']['rajju'], 1.0)
        self.assertEqual(out['koota_points']['rasi'], 1.0)
        self.assertEqual(out['koota_points']['rasi_adhipathi'], 1.0)
        self.assertEqual(out['koota_points']['vasya'], 0.0)
        self.assertEqual(out['score'], 7.0)

    def test_sample_rohini_shatabhisha_matches_prokerala(self):
        bride = _h(
            nakshatra='Rohini',
            rasi='Vrishabha',
            gana='Manushya',
            yoni='Serpent',
            rajju='Kanta',
        )
        groom = _h(
            nakshatra='Shatabhisha',
            rasi='Kumbha',
            gana='Rakshasa',
            yoni='Horse',
            rajju='Kanta',
        )
        out = calculate_porutham(bride, groom)
        self.assertEqual(out['koota_points']['dina'], 0.0)
        self.assertEqual(out['koota_points']['gana'], 0.5)
        self.assertEqual(out['koota_points']['mahendra'], 0.0)
        self.assertEqual(out['koota_points']['sthree_deergha'], 1.0)
        self.assertEqual(out['koota_points']['yoni'], 0.5)
        self.assertEqual(out['koota_points']['vedha'], 1.0)
        self.assertEqual(out['koota_points']['rajju'], 1.0)
        self.assertEqual(out['koota_points']['rasi'], 1.0)
        self.assertEqual(out['koota_points']['rasi_adhipathi'], 1.0)
        self.assertEqual(out['koota_points']['vasya'], 0.0)
        self.assertEqual(out['score'], 6.0)

    def test_sample_purva_phalguni_shatabhisha_matches_prokerala(self):
        bride = _h(
            nakshatra='Purva Phalguni',
            rasi='Simha',
            gana='Manushya',
            yoni='Cow',
            rajju='Pada',
        )
        groom = _h(
            nakshatra='Shatabhisha',
            rasi='Kumbha',
            gana='Rakshasa',
            yoni='Horse',
            rajju='Pada',
        )
        out = calculate_porutham(bride, groom)
        self.assertEqual(out['koota_points']['dina'], 0.0)
        self.assertEqual(out['koota_points']['gana'], 0.5)
        self.assertEqual(out['koota_points']['mahendra'], 0.0)
        self.assertEqual(out['koota_points']['sthree_deergha'], 0.5)
        self.assertEqual(out['koota_points']['yoni'], 0.5)
        self.assertEqual(out['koota_points']['vedha'], 1.0)
        self.assertEqual(out['koota_points']['rajju'], 1.0)
        self.assertEqual(out['koota_points']['rasi'], 1.0)
        self.assertEqual(out['koota_points']['rasi_adhipathi'], 0.0)
        self.assertEqual(out['koota_points']['vasya'], 0.0)
        self.assertEqual(out['score'], 4.5)

    def test_sample_vishakha_shatabhisha_matches_prokerala(self):
        bride = _h(
            nakshatra='Vishakha',
            rasi='Tula',
            gana='Rakshasa',
            yoni='Tiger',
            rajju='Pada',
        )
        groom = _h(
            nakshatra='Shatabhisha',
            rasi='Kumbha',
            gana='Rakshasa',
            yoni='Horse',
            rajju='Pada',
        )
        out = calculate_porutham(bride, groom)
        self.assertEqual(out['koota_points']['dina'], 1.0)
        self.assertEqual(out['koota_points']['gana'], 1.0)
        self.assertEqual(out['koota_points']['mahendra'], 0.0)
        self.assertEqual(out['koota_points']['sthree_deergha'], 0.0)
        self.assertEqual(out['koota_points']['yoni'], 0.0)
        self.assertEqual(out['koota_points']['vedha'], 1.0)
        self.assertEqual(out['koota_points']['rajju'], 1.0)
        self.assertEqual(out['koota_points']['rasi'], 0.0)
        self.assertEqual(out['koota_points']['rasi_adhipathi'], 1.0)
        self.assertEqual(out['koota_points']['vasya'], 0.0)
        self.assertEqual(out['score'], 5.0)

    def test_score_sum_matches_koota_points(self):
        bride = _h()
        groom = _h(nakshatra='Magha', rasi='Simha', yoni='Rat', rajju='Sira')
        out = calculate_porutham(bride, groom)
        s = sum(out['koota_points'].values())
        self.assertAlmostEqual(out['score'], round(s, 2), places=2)

    def test_gana_is_derived_from_nakshatra_when_available(self):
        bride = _h(nakshatra='Purva Phalguni', gana='Deva')
        groom = _h(nakshatra='Shatabhisha', gana='Deva')
        out = calculate_porutham(bride, groom)
        # Purva Phalguni -> Manushya, Shatabhisha -> Rakshasa => 0.5
        self.assertEqual(out['koota_points']['gana'], 0.5)


if __name__ == '__main__':
    unittest.main()
