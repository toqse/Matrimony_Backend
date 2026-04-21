"""Bride/groom horoscope ordering for match UI (gender + blanks)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from astrology.services.generate_ui_service import resolve_bride_groom_horoscopes


def _prof(gender_primary: str, gender_partner: str):
    return (
        SimpleNamespace(user=SimpleNamespace(gender=gender_primary)),
        SimpleNamespace(user=SimpleNamespace(gender=gender_partner)),
    )


class BrideGroomResolutionTests(unittest.TestCase):
    def test_f_m_primary_is_bride(self):
        p, o = _prof('F', 'M')
        b, g = resolve_bride_groom_horoscopes(p, o, 'B', 'G')
        self.assertEqual(b, 'B')
        self.assertEqual(g, 'G')

    def test_m_f_partner_is_bride(self):
        p, o = _prof('M', 'F')
        b, g = resolve_bride_groom_horoscopes(p, o, 'B', 'G')
        self.assertEqual(b, 'G')
        self.assertEqual(g, 'B')

    def test_m_primary_partner_gender_blank_female_is_bride(self):
        """Staff views male profile first; partner female — must not treat male as bride."""
        p, o = _prof('M', '')
        b, g = resolve_bride_groom_horoscopes(p, o, 'male_h', 'partner_h')
        self.assertEqual(b, 'partner_h')
        self.assertEqual(g, 'male_h')

    def test_blank_primary_f_partner_is_bride(self):
        p, o = _prof('', 'F')
        b, g = resolve_bride_groom_horoscopes(p, o, 'primary_h', 'partner_h')
        self.assertEqual(b, 'partner_h')
        self.assertEqual(g, 'primary_h')


if __name__ == '__main__':
    unittest.main()
