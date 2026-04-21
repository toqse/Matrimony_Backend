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
    NAKSHATRA_YONI,
    PAIR_POINT_OVERRIDES,
    _VEDHA_PAIRS,
    _YONI_ENEMIES,
    dina_points,
    distance,
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
        "label": "Sisira(Dhanishta/Makara) vs Unnikrishnan(Chitra/Tula) — 2026-04-20",
        "bride": {"nakshatra": "Dhanishta", "rasi": "Makara"},
        "groom": {"nakshatra": "Chitra", "rasi": "Tula"},
        "expected": {
            "dina": 1.0,
            "gana": 1.0,
            "mahendra": 1.0,
            "sthree_deergha": 1.0,
            "yoni": 0.5,
            "vedha": 0.0,
            "rajju": 1.0,
            "vasya": 1.0,
            "rasi": 1.0,
            "rasi_adhipathi": 1.0,
            "total": 8.5,
        },
    },
    {
        "label": "Pooyam(Pushya/Karka) vs Chithira(Chitra/Tula) — 2026-04-21",
        "bride": {"nakshatra": "Pushya", "rasi": "Karka"},
        "groom": {"nakshatra": "Chitra", "rasi": "Tula"},
        "expected": {
            "dina": 0.0,
            "gana": 0.0,
            "mahendra": 1.0,
            "sthree_deergha": 0.0,
            "yoni": 0.0,
            "vedha": 1.0,
            "rajju": 0.0,
            "vasya": 0.0,
            "rasi": 0.0,
            "rasi_adhipathi": 0.0,
            "total": 2.0,
        },
    },
    {
        "label": "Rajalekshmi(Bharani/Mesha) vs Kasyap(Shatabhisha/Kumbha) — 2026-04-21",
        "bride": {"nakshatra": "Bharani", "rasi": "Mesha"},
        "groom": {"nakshatra": "Shatabhisha", "rasi": "Kumbha"},
        "expected": {
            "dina": 0.0,
            "gana": 0.5,
            "mahendra": 0.0,
            "sthree_deergha": 1.0,
            "yoni": 0.0,
            "vedha": 1.0,
            "rajju": 1.0,
            "vasya": 1.0,
            "rasi": 1.0,
            "rasi_adhipathi": 0.0,
            "total": 5.5,
        },
    },
    {
        "label": "Rajalekshmi(Bharani/Mesha) vs Amalnath(Ardra/Mithuna) — 2026-04-21",
        "bride": {"nakshatra": "Bharani", "rasi": "Mesha"},
        "groom": {"nakshatra": "Ardra", "rasi": "Mithuna"},
        "expected": {
            "dina": 0.0,
            "gana": 1.0,
            "mahendra": 0.0,
            "sthree_deergha": 0.0,
            "yoni": 0.0,
            "vedha": 1.0,
            "rajju": 1.0,
            "vasya": 0.0,
            "rasi": 0.0,
            "rasi_adhipathi": 1.0,
            "total": 4.0,
        },
    },
    {
        "label": "Anupriya(Vishakha/Tula) vs Amalnath(Ardra/Mithuna) — 2026-04-21",
        "bride": {"nakshatra": "Vishakha", "rasi": "Tula"},
        "groom": {"nakshatra": "Ardra", "rasi": "Mithuna"},
        "expected": {
            "dina": 1.0,
            "gana": 0.0,
            "mahendra": 0.0,
            "sthree_deergha": 1.0,
            "yoni": 0.0,
            "vedha": 1.0,
            "rajju": 1.0,
            "vasya": 0.0,
            "rasi": 1.0,
            "rasi_adhipathi": 1.0,
            "total": 6.0,
        },
    },
    {
        "label": "Sisira(Dhanishta/Makara) vs Amalnath(Ardra/Mithuna) — 2026-04-21",
        "bride": {"nakshatra": "Dhanishta", "rasi": "Makara"},
        "groom": {"nakshatra": "Ardra", "rasi": "Mithuna"},
        "expected": {
            "dina": 1.0,
            "gana": 1.0,
            "mahendra": 0.0,
            "sthree_deergha": 1.0,
            "yoni": 0.5,
            "vedha": 0.0,
            "rajju": 1.0,
            "rasi": 0.0,
            "rasi_adhipathi": 1.0,
            "vasya": 0.0,
            "total": 5.5,
        },
    },
    {
        "label": "Vaishnava(Chitra/Kanya) vs Abhinav(Krittika/Mesha) — 2026-04-21",
        "bride": {"nakshatra": "Chitra", "rasi": "Kanya"},
        "groom": {"nakshatra": "Krittika", "rasi": "Mesha"},
        "expected": {
            "dina": 1.0,
            "gana": 0.5,
            "mahendra": 0.0,
            "sthree_deergha": 1.0,
            "yoni": 0.5,
            "vedha": 1.0,
            "rajju": 1.0,
            "vasya": 0.0,
            "rasi": 0.5,
            "rasi_adhipathi": 1.0,
            "total": 6.5,
        },
    },
    {
        "label": "Rajalekshmi(Bharani/Mesha) vs Abhinav(Krittika/Mesha) — 2026-04-21",
        "bride": {"nakshatra": "Bharani", "rasi": "Mesha"},
        "groom": {"nakshatra": "Krittika", "rasi": "Mesha"},
        "expected": {
            "dina": 1.0,
            "gana": 0.5,
            "mahendra": 0.0,
            "sthree_deergha": 0.0,
            "yoni": 0.0,
            "vedha": 1.0,
            "rajju": 1.0,
            "vasya": 0.0,
            "rasi": 1.0,
            "rasi_adhipathi": 1.0,
            "total": 5.5,
        },
    },
]

class PoruthamRegressionTests(unittest.TestCase):
    def test_verified_pairs_exact(self):
        for row in VERIFIED_PAIRS:
            with self.subTest(pair=row["label"]):
                bride = _h(row["bride"]["nakshatra"], row["bride"]["rasi"])
                groom = _h(row["groom"]["nakshatra"], row["groom"]["rasi"])

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
                expected = {k: v for k, v in row["expected"].items() if k != "total"}
                if actual != expected:
                    self.fail("Koota diff:\n" + _diff(expected, actual))

                total = round(sum(actual.values()), 2)
                self.assertEqual(total, row["expected"]["total"])

    def test_dhanishta_ardra_koota_spotcheck(self):
        self.assertEqual(dina_points("Dhanishta", "Ardra"), 1.0)
        self.assertEqual(gana_points("Rakshasa", "Manushya"), 0.0)
        self.assertEqual(sthree_deergha_points("Dhanishta", "Ardra"), 1.0)
        self.assertEqual(yoni_points("Dhanishta", "Ardra"), 0.5)
        self.assertEqual(rajju_points("Dhanishta", "Ardra"), 1.0)

    def test_dina_verify_block(self):
        self.assertEqual(dina_points("Pushya", "Chitra"), 0.0)
        self.assertEqual(dina_points("Dhanishta", "Chitra"), 1.0)
        self.assertEqual(dina_points("Revati", "Ashwini"), 1.0)
        self.assertEqual(dina_points("Rohini", "Shatabhisha"), 0.0)
        self.assertEqual(dina_points("Ashwini", "Ashwini"), 1.0)
        self.assertEqual(dina_points("Rohini", "Ashwini"), 0.0)

    def test_gana_verify_block(self):
        self.assertEqual(gana_points("Rakshasa", "Manushya"), 0.0)
        self.assertEqual(gana_points("Manushya", "Rakshasa"), 0.5)
        self.assertEqual(gana_points("Deva", "Manushya"), 0.0)
        self.assertEqual(gana_points("Manushya", "Deva"), 1.0)
        self.assertEqual(gana_points("Deva", "Deva"), 1.0)
        self.assertEqual(gana_points("Rakshasa", "Rakshasa"), 1.0)

    def test_sthree_deergha_verify_block(self):
        self.assertEqual(sthree_deergha_points("Vishakha", "Ardra"), 1.0)
        self.assertEqual(sthree_deergha_points("Dhanishta", "Chitra"), 1.0)
        self.assertEqual(sthree_deergha_points("Pushya", "Chitra"), 0.0)
        self.assertEqual(sthree_deergha_points("Bharani", "Shatabhisha"), 1.0)
        self.assertEqual(sthree_deergha_points("Bharani", "Ardra"), 0.0)

    def test_dina_count_17_good(self):
        self.assertEqual(dina_points("Chitra", "Krittika"), 1.0)

    def test_yoni_verify_block(self):
        self.assertEqual(yoni_points("Pushya", "Chitra"), 0.0)
        self.assertEqual(yoni_points("Vishakha", "Chitra"), 0.0)
        self.assertEqual(yoni_points("Dhanishta", "Chitra"), 0.5)
        self.assertEqual(yoni_points("Chitra", "Vishakha"), 1.0)
        self.assertEqual(yoni_points("Shatabhisha", "Ashwini"), 1.0)
        self.assertEqual(yoni_points("Ashwini", "Hasta"), 0.0)
        self.assertEqual(yoni_points("Magha", "Ashlesha"), 0.0)
        self.assertEqual(yoni_points("Rohini", "Uttara Ashadha"), 0.0)

    def test_rajju_verify_block(self):
        self.assertEqual(rajju_points("Dhanishta", "Chitra"), 1.0)
        self.assertEqual(rajju_points("Pushya", "Chitra"), 0.0)
        self.assertEqual(rajju_points("Chitra", "Dhanishta"), 1.0)
        self.assertEqual(rajju_points("Bharani", "Chitra"), 0.0)
        self.assertEqual(rajju_points("Bharani", "Dhanishta"), 1.0)
        self.assertEqual(rajju_points("Pushya", "Dhanishta"), 1.0)
        self.assertEqual(rajju_points("Mrigashirsha", "Chitra"), 1.0)
        self.assertEqual(rajju_points("Mrigashirsha", "Dhanishta"), 0.0)
        self.assertEqual(rajju_points("Mrigashirsha", "Pushya"), 1.0)
        self.assertEqual(rajju_points("Ashwini", "Magha"), 1.0)
        self.assertEqual(rajju_points("Ashwini", "Chitra"), 1.0)
        self.assertEqual(rajju_points("Revati", "Dhanishta"), 1.0)
        self.assertEqual(rajju_points("Krittika", "Vishakha"), 1.0)
        self.assertEqual(rajju_points("Krittika", "Chitra"), 1.0)
        self.assertEqual(rajju_points("Rohini", "Shravana"), 1.0)
        self.assertEqual(rajju_points("Rohini", "Chitra"), 1.0)
        self.assertEqual(rajju_points("Vishakha", "Krittika"), 1.0)

    def test_rasi_verify_block(self):
        self.assertEqual(rasi_points("Makara", "Tula"), 1.0)
        self.assertEqual(rasi_points("Karka", "Tula"), 0.0)
        self.assertEqual(rasi_points("Mesha", "Kumbha"), 1.0)
        self.assertEqual(rasi_points("Mesha", "Mithuna"), 0.0)
        self.assertEqual(rasi_points("Tula", "Mithuna"), 1.0)
        self.assertEqual(rasi_points("Makara", "Mithuna"), 0.0)
        self.assertEqual(rasi_points("Kanya", "Mesha"), 0.5)
        self.assertEqual(rasi_points("Mesha", "Mesha"), 1.0)
        self.assertEqual(rasi_points("Tula", "Mesha"), 1.0)

    def test_vasya_verify_block(self):
        self.assertEqual(vasya_points("Mesha", "Kumbha"), 1.0)
        self.assertEqual(vasya_points("Kumbha", "Mesha"), 1.0)
        self.assertEqual(vasya_points("Tula", "Mesha"), 0.0)
        self.assertEqual(vasya_points("Tula", "Makara"), 1.0)
        self.assertEqual(vasya_points("Makara", "Kumbha"), 1.0)
        self.assertEqual(vasya_points("Makara", "Mesha"), 1.0)
        self.assertEqual(vasya_points("Simha", "Kumbha"), 0.0)
        self.assertEqual(vasya_points("Dhanus", "Meena"), 0.0)

    def test_rasyadhipathi_verify_block(self):
        self.assertEqual(rasyadhipathi_points("Makara", "Tula"), 1.0)
        self.assertEqual(rasyadhipathi_points("Karka", "Tula"), 0.0)
        self.assertEqual(rasyadhipathi_points("Mesha", "Kumbha"), 0.0)
        self.assertEqual(rasyadhipathi_points("Mesha", "Mithuna"), 1.0)
        self.assertEqual(rasyadhipathi_points("Mesha", "Mesha"), 1.0)
        self.assertEqual(rasyadhipathi_points("Kanya", "Mithuna"), 1.0)

    def test_computed_729_spotcheck_and_consistency(self):
        p = Path(__file__).resolve().parent / "computed_729.json"
        self.assertTrue(p.exists(), msg="computed_729.json missing; run generate_computed_729.py")
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(len(data), 729)

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
            if row["rajju"] == 0.0:
                self.assertEqual(kp["rajju"], 0.0)

    def test_symmetry_kootas(self):
        # Dina / gana / mahendra / sthree_deergha / vedha / rasyadhipathi are directional.
        for b in NAKSHATRA_ORDER:
            for g in NAKSHATRA_ORDER:
                bride = _h(b)
                groom = _h(g)

                v1 = {
                    "rajju": rajju_points(bride.nakshatra, groom.nakshatra),
                    "vasya": vasya_points(bride.rasi, groom.rasi),
                }
                v2 = {
                    "rajju": rajju_points(groom.nakshatra, bride.nakshatra),
                    "vasya": vasya_points(groom.rasi, bride.rasi),
                }
                if v1 != v2:
                    self.fail(f"symmetry failed {b} vs {g}:\n" + _diff(v2, v1))

    def test_rajju_kati_and_sira_dosha_pairs(self):
        self.assertEqual(rajju_points("Bharani", "Pushya"), 0.0)
        self.assertEqual(rajju_points("Bharani", "Chitra"), 0.0)
        self.assertEqual(rajju_points("Pushya", "Chitra"), 0.0)
        self.assertEqual(rajju_points("Mrigashirsha", "Dhanishta"), 0.0)
        self.assertEqual(rajju_points("Bharani", "Bharani"), 0.0)

    def test_yoni_enemy_pairs_always_zero(self):
        self.assertEqual(yoni_points("Ashwini", "Hasta"), 0.0)
        self.assertEqual(yoni_points("Magha", "Ashlesha"), 0.0)
        self.assertEqual(yoni_points("Pushya", "Chitra"), 0.0)

    def test_yoni_enemy_all_pairs_zero(self):
        for e in _YONI_ENEMIES:
            animals = tuple(e)
            if len(animals) != 2:
                continue
            a1, a2 = animals
            b_naks = [n for n, (an, _) in NAKSHATRA_YONI.items() if an == a1]
            g_naks = [n for n, (an, _) in NAKSHATRA_YONI.items() if an == a2]
            self.assertTrue(b_naks and g_naks, msg=f"missing nak for {a1}/{a2}")
            self.assertEqual(yoni_points(b_naks[0], g_naks[0]), 0.0)

    def test_yoni_vikara_all_male_bride_female_groom_zero(self):
        male_brides = [n for n in NAKSHATRA_ORDER if NAKSHATRA_YONI.get(n, ("", ""))[1] == "Male"]
        female_grooms = [n for n in NAKSHATRA_ORDER if NAKSHATRA_YONI.get(n, ("", ""))[1] == "Female"]
        for b in male_brides:
            for g in female_grooms:
                self.assertEqual(yoni_points(b, g), 0.0, msg=f"{b} vs {g}")

    def test_vedha_verify_block(self):
        self.assertEqual(vedha_points("Chitra", "Krittika"), 1.0)
        self.assertEqual(vedha_points("Vishakha", "Krittika"), 0.0)
        self.assertEqual(vedha_points("Krittika", "Vishakha"), 0.0)
        self.assertEqual(vedha_points("Mrigashirsha", "Chitra"), 0.0)
        self.assertEqual(vedha_points("Dhanishta", "Chitra"), 0.0)
        self.assertEqual(vedha_points("Ashwini", "Jyeshtha"), 0.0)
        self.assertEqual(vedha_points("Bharani", "Anuradha"), 0.0)
        self.assertEqual(vedha_points("Rohini", "Swati"), 0.0)
        self.assertEqual(vedha_points("Ashwini", "Bharani"), 1.0)
        self.assertGreaterEqual(len(_VEDHA_PAIRS), 13)

    def test_dina_wrap_revati_ashwini(self):
        self.assertEqual(distance("Revati", "Ashwini"), 1)
        self.assertEqual(dina_points("Revati", "Ashwini"), 1.0)

    def test_pair_point_overrides_regression(self):
        for (b, g), expected in PAIR_POINT_OVERRIDES.items():
            with self.subTest(pair=f"{b} vs {g}"):
                out = calculate_porutham(_h(b), _h(g))
                self.assertEqual(
                    out["koota_points"],
                    expected,
                    msg="override mismatch:\n" + _diff(expected, out["koota_points"]),
                )


if __name__ == "__main__":
    unittest.main()
