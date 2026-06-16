"""VB dashakoot porutham (astrology.porutham) smoke tests."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from astrology.porutham import PAPA_SAMYAM_TOLERANCE, papa_samyam
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


class PapaSamyamToleranceTests(unittest.TestCase):
    def test_equal_scores_pass(self):
        self.assertTrue(papa_samyam(20.0, 20.0))

    def test_within_tolerance_pass(self):
        self.assertTrue(papa_samyam(20.0, 20.0 + PAPA_SAMYAM_TOLERANCE))

    def test_known_exe_fail_case(self):
        # bride 25.5 vs groom 50.5 (|diff| = 25) -> EXE FAIL
        self.assertFalse(papa_samyam(25.5, 50.5))

    def test_symmetric(self):
        self.assertEqual(papa_samyam(50.5, 25.5), papa_samyam(25.5, 50.5))

    def test_none_inputs_pass(self):
        self.assertTrue(papa_samyam(None, None))


class DoshaGradeDemotionTests(unittest.TestCase):
    """The three dosha checks only demote overall_result; they must NOT change
    the 10-porutham grades, booleans, counts, or score."""

    def _base_pair(self):
        # Two charts with full chart strings so chovva_dosham is not None.
        bride = SimpleNamespace(pr_star=5, pr_pada=4, pr_rasi='ABCDEFGHIJK')
        groom = SimpleNamespace(pr_star=7, pr_pada=1, pr_rasi='ABCDEFGHIJK')
        return bride, groom

    def test_ten_porutham_outputs_unaffected_by_dosha(self):
        bride, groom = self._base_pair()
        out = calculate_porutham(bride, groom)
        grade_keys = [
            'dinam', 'ganam', 'mahendra', 'sthree_deerga', 'yoni',
            'rasi', 'rasyadhipam', 'vasyam', 'rajju_dosham', 'vedha_dosham',
        ]
        # Snapshot the 10-porutham outputs.
        grades = {k: out[k] for k in grade_keys}
        poruthams = dict(out['poruthams'])
        counts = (
            out['uthamam_count'], out['madhyamam_count'],
            out['adhamam_count'], out['total_porutham_count'],
        )
        score = (out['score'], out['max_score'])

        # The 10-koota count/score never exceed their bounds and stay coherent.
        self.assertEqual(out['max_score'], 10)
        self.assertEqual(out['score'], out['uthamam_count'])
        self.assertEqual(
            out['uthamam_count'],
            sum(1 for k in grade_keys if poruthams[k]),
        )
        # Re-running yields identical 10-porutham outputs (deterministic).
        out2 = calculate_porutham(bride, groom)
        self.assertEqual({k: out2[k] for k in grade_keys}, grades)
        self.assertEqual(out2['poruthams'], poruthams)
        self.assertEqual(
            (
                out2['uthamam_count'], out2['madhyamam_count'],
                out2['adhamam_count'], out2['total_porutham_count'],
            ),
            counts,
        )
        self.assertEqual((out2['score'], out2['max_score']), score)

    def test_overall_result_demoted_when_dosha_fails(self):
        bride, groom = self._base_pair()
        out = calculate_porutham(bride, groom)
        tiers = ['Not Recommended', 'Average', 'Good', 'Excellent']
        u = out['uthamam_count']
        base_tier = 3 if u >= 8 else 2 if u >= 6 else 1 if u >= 4 else 0
        demotion = (
            (1 if out['chovva_dosham'] is False else 0)
            + (1 if out['papa_samyam'] is False else 0)
            + (1 if out['dasa_sandhi'] is False else 0)
        )
        self.assertEqual(out['overall_result'], tiers[max(0, base_tier - demotion)])


if __name__ == '__main__':
    unittest.main()
