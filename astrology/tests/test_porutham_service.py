"""VB dashakoot porutham (astrology.porutham) smoke tests."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from astrology.services.porutham_service import calculate_porutham


def _chart_moon_rasi(moon_sign: int) -> str:
    parts = []
    for i in range(11):
        parts.append(chr(ord('A') + moon_sign - 1) if i == 2 else 'A')
    return ''.join(parts)


def _hp(*, star: int, pada: int = 1, moon: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        pr_star=star,
        pr_pada=pada,
        pr_rasi=_chart_moon_rasi(moon),
    )


class VbPoruthamSmokeTests(unittest.TestCase):
    def test_returns_expected_keys(self):
        bride = _hp(star=5, pada=4, moon=3)
        groom = _hp(star=7, pada=1, moon=3)
        out = calculate_porutham(bride, groom)
        for k in (
            'dinam', 'ganam', 'mahendra', 'sthree_deerga', 'yoni',
            'rasi', 'rasyadhipam', 'vasyam', 'rajju_dosham', 'vedha_dosham',
            'chovva_dosham', 'bride_papatha', 'groom_papatha',
            'papa_samyam', 'dasa_sandhi',
            'poruthams', 'score', 'max_score', 'result', 'overall_result',
        ):
            self.assertIn(k, out)
        self.assertIsInstance(out['poruthams'], dict)

    def test_revati_ashwini_pair(self):
        bride = _hp(star=27, pada=4, moon=12)
        groom = _hp(star=1, pada=1, moon=1)
        out = calculate_porutham(bride, groom)
        self.assertGreaterEqual(out['uthamam_count'], 0)
        self.assertLessEqual(out['uthamam_count'], 10)


if __name__ == '__main__':
    unittest.main()
