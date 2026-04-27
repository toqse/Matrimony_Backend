import unittest
from types import SimpleNamespace

from astrology.services.porutham_service import calculate_porutham


class ReferenceMatchFlowTests(unittest.TestCase):
    def test_reference_pair_porutham_flags_match_legacy_snapshot(self):
        # Legacy screenshot pair:
        # Bride  -> Mrigashirsha (Makayiram), Pada 4, Rasi Mithuna
        # Groom  -> Punarvasu (Punartham), Pada 1, Rasi Mithuna
        bride = SimpleNamespace(nakshatra='Mrigashirsha', rasi='Mithuna', gana='Deva')
        groom = SimpleNamespace(nakshatra='Punarvasu', rasi='Mithuna', gana='Deva')
        out = calculate_porutham(bride, groom)
        p = out['poruthams']
        kp = out['koota_points']

        self.assertTrue(p['rasi'])
        self.assertTrue(p['rasi_adhipathi'])
        self.assertFalse(p['vasya'])
        self.assertFalse(p['sthree_deergha'])
        self.assertFalse(p['dina'])
        self.assertFalse(p['mahendra'])
        self.assertTrue(p['gana'])
        self.assertTrue(p['yoni'])
        self.assertTrue(p['rajju'])
        self.assertTrue(p['vedha'])
        self.assertEqual(kp['yoni'], 0.5)


if __name__ == '__main__':
    unittest.main()
