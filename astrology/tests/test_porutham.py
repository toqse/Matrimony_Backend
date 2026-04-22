"""
Regression tests for Prokerala-verified porutham pairs.

Run:
  python manage.py test astrology.tests.test_porutham
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from astrology.services.porutham_service import calculate_porutham


def _h(**kwargs):
    """
    Minimal horoscope-like object for calculate_porutham().
    calculate_porutham derives gana from nakshatra when possible, so defaults here
    are only used as fallbacks.
    """
    defaults = dict(
        nakshatra='Rohini',
        rasi='Vrishabha',
        gana='Manushya',
        yoni='Serpent',
        rajju='Kanta',
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _diff_scores(expected: dict[str, float], actual: dict[str, float]) -> str:
    keys = sorted(set(expected) | set(actual))
    lines: list[str] = []
    for k in keys:
        ev = expected.get(k, None)
        av = actual.get(k, None)
        if ev != av:
            lines.append(f"- {k}: expected={ev!r} actual={av!r}")
    return "\n".join(lines) if lines else "(no diff)"


class ProkeralaPoruthamRegressionTests(unittest.TestCase):
    def test_prokerala_verified_pairs(self):
        pairs = [
            {
                "name": "Sisira(Dhanishta,Makara)_vs_Unnikrishnan(Chitra,Tula)",
                "bride": _h(nakshatra="Dhanishta", rasi="Makara"),
                "groom": _h(nakshatra="Chitra", rasi="Tula"),
                "expected_points": {
                    "dina": 1.0,
                    "gana": 1.0,
                    "mahendra": 1.0,
                    "sthree_deergha": 0.0,
                    "yoni": 0.5,
                    "vedha": 0.0,
                    "rajju": 1.0,
                    "vasya": 1.0,
                    "rasi": 1.0,
                    "rasi_adhipathi": 1.0,
                },
                "expected_score": 7.5,
            },
        ]

        for row in pairs:
            with self.subTest(pair=row["name"]):
                out = calculate_porutham(row["bride"], row["groom"])
                actual_points = out.get("koota_points") or {}

                self.assertIsInstance(actual_points, dict)
                for k in row["expected_points"].keys():
                    self.assertIn(k, actual_points, msg=f"Missing koota key: {k}")

                if actual_points != row["expected_points"]:
                    self.fail(
                        "Koota points mismatch:\n"
                        + _diff_scores(row["expected_points"], actual_points)
                    )

                self.assertEqual(
                    out.get("score"),
                    row["expected_score"],
                    msg=f"Total score mismatch (expected {row['expected_score']}, got {out.get('score')})",
                )


if __name__ == "__main__":
    unittest.main()

