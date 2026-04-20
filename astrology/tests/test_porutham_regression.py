"""
Porutham regression + mathematical self-checks.

Run:
  python manage.py test astrology.tests.test_porutham_regression --verbosity=2
"""

from __future__ import annotations

import json
import random
import unittest
from pathlib import Path
from types import SimpleNamespace

from astrology.services.nakshatra_data import NAKSHATRA_MAP
from astrology.services.porutham_service import calculate_porutham
from astrology.services.prokerala_dashakoot_tables import (
    NAKSHATRA_ORDER,
    PAIR_POINT_OVERRIDES,
    dina_points,
    gana_points,
    mahendra_points,
    rajju_points,
    rasi_points,
    rasyadhipathi_points,
    sthree_deergha_points,
    vasya_points,
    vedha_points,
    yoni_points,
)


def _nak_rasi(n: str) -> str:
    r = (NAKSHATRA_MAP[n].get("rasi") or "").split("/")[0].strip()
    return r or "Mesha"


def _h(nak: str, rasi: str | None = None):
    return SimpleNamespace(
        nakshatra=nak,
        rasi=(rasi or _nak_rasi(nak)),
        gana=NAKSHATRA_MAP[nak].get("gana", ""),
        yoni=NAKSHATRA_MAP[nak].get("yoni", ""),
        rajju=NAKSHATRA_MAP[nak].get("rajju", ""),
    )


def _diff(expected: dict[str, float], actual: dict[str, float]) -> str:
    keys = sorted(set(expected) | set(actual))
    lines = []
    for k in keys:
        ev = expected.get(k, None)
        av = actual.get(k, None)
        if ev != av:
            lines.append(f"{k}: expected={ev!r} actual={av!r}")
    return "\n".join(lines) if lines else "(no diff)"


VERIFIED_PAIRS = [
    {
        "name": "Sisira(Dhanishta/Makara)_vs_Unnikrishnan(Chitra/Tula)",
        "bride": {"nakshatra": "Dhanishta", "rasi": "Makara"},
        "groom": {"nakshatra": "Chitra", "rasi": "Tula"},
        "expected_points": {
            "dina": 1.0,
            "gana": 1.0,
            "mahendra": 1.0,
            "sthree_deergha": 1.0,
            "yoni": 0.5,
            "vedha": 0.0,
            "rajju": 0.0,
            "vasya": 1.0,
            "rasi": 1.0,
            "rasi_adhipathi": 1.0,
        },
        "expected_total": 7.5,
    },
]


class PoruthamRegressionTests(unittest.TestCase):
    def test_verified_pairs_exact(self):
        for row in VERIFIED_PAIRS:
            with self.subTest(pair=row["name"]):
                bride = _h(row["bride"]["nakshatra"], row["bride"]["rasi"])
                groom = _h(row["groom"]["nakshatra"], row["groom"]["rasi"])

                # Call scoring functions directly (not through API).
                bride_gana = NAKSHATRA_MAP[bride.nakshatra]["gana"]
                groom_gana = NAKSHATRA_MAP[groom.nakshatra]["gana"]
                actual = {
                    "dina": dina_points(bride.nakshatra, groom.nakshatra),
                    "gana": gana_points(bride_gana, groom_gana),
                    "mahendra": mahendra_points(bride.nakshatra, groom.nakshatra),
                    "sthree_deergha": sthree_deergha_points(bride.nakshatra, groom.nakshatra),
                    "yoni": yoni_points(bride.nakshatra, groom.nakshatra),
                    "vedha": vedha_points(bride.nakshatra, groom.nakshatra),
                    "rajju": rajju_points(bride.nakshatra, groom.nakshatra),
                    "vasya": vasya_points(bride.rasi, groom.rasi),
                    "rasi": rasi_points(bride.rasi, groom.rasi),
                    "rasi_adhipathi": rasyadhipathi_points(bride.rasi, groom.rasi),
                }
                expected = row["expected_points"]
                if actual != expected:
                    self.fail("Koota diff:\n" + _diff(expected, actual))

                total = round(sum(actual.values()), 2)
                self.assertEqual(total, row["expected_total"])

    def test_computed_729_spotcheck_and_consistency(self):
        p = Path(__file__).resolve().parent / "computed_729.json"
        self.assertTrue(p.exists(), msg="computed_729.json missing; run generate_computed_729.py")
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(len(data), 729)

        # Spot-check 10 deterministic random pairs for internal consistency.
        rng = random.Random(1337)
        keys = list(data.keys())
        for _ in range(10):
            key = rng.choice(keys)
            row = data[key]
            bride = _h(row["bride"], row["bride_rasi"])
            groom = _h(row["groom"], row["groom_rasi"])
            out = calculate_porutham(bride, groom)
            kp = out["koota_points"]
            self.assertAlmostEqual(row["total"], out["score"], places=2)
            # Rajju consistency
            if row["rajju"] == 0.0:
                self.assertEqual(kp["rajju"], 0.0)

    def test_symmetry_kootas(self):
        # swap bride/groom: these must match.
        # IMPORTANT: Use raw scoring functions (not calculate_porutham), so pair overrides
        # cannot break the symmetry checks.
        #
        # Note: rasi_points() is directional by definition (diff = (bride-groom)%12),
        # so it is intentionally excluded from symmetry checks.
        for b in NAKSHATRA_ORDER:
            for g in NAKSHATRA_ORDER:
                bride = _h(b)
                groom = _h(g)
                bg = NAKSHATRA_MAP[bride.nakshatra]["gana"]
                gg = NAKSHATRA_MAP[groom.nakshatra]["gana"]

                v1 = {
                    "gana": gana_points(bg, gg),
                    "mahendra": mahendra_points(bride.nakshatra, groom.nakshatra),
                    "vedha": vedha_points(bride.nakshatra, groom.nakshatra),
                    "rajju": rajju_points(bride.nakshatra, groom.nakshatra),
                    "rasi_adhipathi": rasyadhipathi_points(bride.rasi, groom.rasi),
                    "vasya": vasya_points(bride.rasi, groom.rasi),
                }
                v2 = {
                    "gana": gana_points(gg, bg),
                    "mahendra": mahendra_points(groom.nakshatra, bride.nakshatra),
                    "vedha": vedha_points(groom.nakshatra, bride.nakshatra),
                    "rajju": rajju_points(groom.nakshatra, bride.nakshatra),
                    "rasi_adhipathi": rasyadhipathi_points(groom.rasi, bride.rasi),
                    "vasya": vasya_points(groom.rasi, bride.rasi),
                }
                if v1 != v2:
                    self.fail(f"symmetry failed {b} vs {g}:\n" + _diff(v2, v1))

    def test_rajju_dosha_group_sira(self):
        # Sira group: Mrigashirsha, Chitra, Dhanishta -> any pair within group is 0.0
        sira = ["Mrigashirsha", "Chitra", "Dhanishta"]
        for i in range(len(sira)):
            for j in range(i + 1, len(sira)):
                self.assertEqual(rajju_points(sira[i], sira[j]), 0.0)

    def test_yoni_enemy_pairs_always_zero(self):
        # (Ashwini,Hasta) = Horse+Buffalo enemy -> 0.0
        self.assertEqual(yoni_points("Ashwini", "Hasta"), 0.0)
        # (Magha,Ashlesha) = Rat+Cat enemy -> 0.0
        self.assertEqual(yoni_points("Magha", "Ashlesha"), 0.0)
        # Bug 19 regression: different animals still trigger Vikara (Male bride + Female groom).
        self.assertEqual(yoni_points("Pushya", "Chitra"), 0.0)

    def test_all_vedha_pairs_blocking(self):
        # Ensure all _VEDHA_PAIRS return 0.0 via known pairs list in spec.
        pairs = [
            ("Ashwini", "Jyeshtha"),
            ("Bharani", "Anuradha"),
            ("Krittika", "Vishakha"),
            ("Rohini", "Swati"),
            ("Mrigashirsha", "Chitra"),
            ("Ardra", "Hasta"),
            ("Punarvasu", "Uttara Phalguni"),
            ("Pushya", "Purva Phalguni"),
            ("Ashlesha", "Magha"),
            ("Mula", "Revati"),
            ("Purva Ashadha", "Uttara Bhadrapada"),
            ("Uttara Ashadha", "Purva Bhadrapada"),
            ("Shravana", "Shatabhisha"),
            ("Dhanishta", "Chitra"),
        ]
        for a, b in pairs:
            self.assertEqual(vedha_points(a, b), 0.0)

    def test_dina_wraparound_examples(self):
        # distance(Revati=26, Ashwini=0) -> count 2 -> good
        self.assertEqual(dina_points("Revati", "Ashwini"), 1.0)
        # distance(Ashwini=0, Revati=26) -> count 27 -> not in good set (unless groom override applies, it doesn't)
        self.assertEqual(dina_points("Ashwini", "Revati"), 0.0)
        # Bug 18 regression: Pushya->Chitra count=7 not in set => 0.0
        self.assertEqual(dina_points("Pushya", "Chitra"), 0.0)

    def test_pair_point_overrides_regression(self):
        # Ensure calculate_porutham returns the override values exactly for all override pairs.
        for (b, g), expected in PAIR_POINT_OVERRIDES.items():
            with self.subTest(pair=f"{b} vs {g}"):
                out = calculate_porutham(_h(b), _h(g))
                self.assertEqual(out["koota_points"], expected, msg="override mismatch:\n" + _diff(expected, out["koota_points"]))


if __name__ == "__main__":
    unittest.main()

