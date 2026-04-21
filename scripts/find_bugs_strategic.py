#!/usr/bin/env python3
"""
Compare local Dashakoot scores (table functions) to Prokerala ground truth from
astrology/tests/ground_truth_strategic.json (produced by fetch_strategic_pairs.py).

Run from repository root (with Django settings):
  python scripts/find_bugs_strategic.py

Docker:
  docker exec -w /app matrimony_backend-django-1 python scripts/find_bugs_strategic.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
GROUND_TRUTH = REPO_ROOT / "astrology" / "tests" / "ground_truth_strategic.json"

KOOTA_KEYS = (
    "dina",
    "gana",
    "mahendra",
    "sthree_deergha",
    "yoni",
    "vedha",
    "rajju",
    "rasi",
    "rasi_adhipathi",
    "vasya",
)


def _setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "matrimony_backend.settings")
    import django

    sys.path.insert(0, str(REPO_ROOT))
    django.setup()


def _nak_rasi(n: str) -> str:
    from astrology.services.nakshatra_data import NAKSHATRA_MAP

    r = (NAKSHATRA_MAP[n].get("rasi") or "").split("/")[0].strip()
    return r or "Mesha"


def _our_koota_points(bride_nak: str, groom_nak: str) -> dict[str, float]:
    """Same scoring path as calculate_porutham without PAIR_POINT_OVERRIDES."""
    from astrology.services.prokerala_dashakoot_tables import (
        dina_points,
        gana_for_nakshatra,
        gana_points,
        mahendra_points,
        rasi_points,
        rasyadhipathi_points,
        rajju_points,
        sthree_deergha_points,
        vasya_points,
        vedha_points,
        yoni_points,
    )

    bride_r = _nak_rasi(bride_nak)
    groom_r = _nak_rasi(groom_nak)
    bride_gana = gana_for_nakshatra(bride_nak, "")
    groom_gana = gana_for_nakshatra(groom_nak, "")
    return {
        "dina": dina_points(bride_nak, groom_nak),
        "gana": gana_points(bride_gana, groom_gana),
        "mahendra": mahendra_points(bride_nak, groom_nak),
        "sthree_deergha": sthree_deergha_points(bride_nak, groom_nak),
        "yoni": yoni_points(bride_nak, groom_nak),
        "vedha": vedha_points(bride_nak, groom_nak),
        "rajju": rajju_points(bride_nak, groom_nak),
        "rasi": rasi_points(bride_r, groom_r),
        "rasi_adhipathi": rasyadhipathi_points(bride_r, groom_r),
        "vasya": vasya_points(bride_r, groom_r),
    }


def main() -> None:
    if not GROUND_TRUTH.exists():
        print(f"Missing {GROUND_TRUTH}. Run scripts/fetch_strategic_pairs.py first.", file=sys.stderr)
        sys.exit(1)

    _setup_django()

    doc = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    pairs = doc.get("pairs") or []
    if not pairs:
        print("ground_truth_strategic.json has no pairs.", file=sys.stderr)
        sys.exit(1)

    by_koota: dict[str, list[str]] = defaultdict(list)
    mismatches = 0

    for row in pairs:
        b = row.get("bride_nakshatra")
        g = row.get("groom_nakshatra")
        pk = row.get("koota_points") or {}
        ours = _our_koota_points(b, g)
        label = f"{b} / {g}"
        for k in KOOTA_KEYS:
            pv = float(pk.get(k, -999))
            ov = float(ours.get(k, -999))
            if abs(pv - ov) > 1e-6:
                mismatches += 1
                msg = f"{label}  {k}: prokerala={pv} ours={ov}  ({row.get('reason', '')})"
                by_koota[k].append(msg)

    print(f"Compared {len(pairs)} pairs. Mismatch count (per koota cell): {mismatches}")
    if not by_koota:
        print("All kootas match within tolerance.")
        return

    print("\n--- Mismatches grouped by koota ---")
    for k in KOOTA_KEYS:
        rows = by_koota.get(k) or []
        if not rows:
            continue
        print(f"\n[{k}] ({len(rows)} mismatches)")
        for line in rows[:40]:
            print(f"  {line}")
        if len(rows) > 40:
            print(f"  ... and {len(rows) - 40} more")


if __name__ == "__main__":
    main()
