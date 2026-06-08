"""Reference pair checks against VB porutham output shape."""
import unittest
from types import SimpleNamespace

from astrology.services.porutham_service import calculate_porutham


def _chart_moon_rasi(moon_sign: int) -> str:
    parts = []
    for i in range(11):
        parts.append(chr(ord('A') + moon_sign - 1) if i == 2 else 'A')
    return ''.join(parts)


class ReferenceMatchFlowTests(unittest.TestCase):
    def test_mriga_punarvasu_mithuna_pair_runs(self):
        bride = SimpleNamespace(
            pr_star=5,
            pr_pada=4,
            pr_rasi=_chart_moon_rasi(3),
        )
        groom = SimpleNamespace(
            pr_star=7,
            pr_pada=1,
            pr_rasi=_chart_moon_rasi(3),
        )
        out = calculate_porutham(bride, groom)
        self.assertIn('poruthams', out)
        self.assertIn('dinam', out)


if __name__ == '__main__':
    unittest.main()
