"""
Generate the 27x27 nakshatra pair matrix JSON.

Run from repo root:
  python astrology/tests/generate_computed_729.py
"""

from __future__ import annotations

import json
from pathlib import Path

from astrology.services.nakshatra_data import NAKSHATRA_MAP
from astrology.services.prokerala_dashakoot_tables import NAKSHATRA_ORDER
from astrology.services.porutham_service import calculate_porutham


def _nak_rasi(n: str) -> str:
    r = (NAKSHATRA_MAP[n].get("rasi") or "").split("/")[0].strip()
    return r or "Mesha"


def _h(nak: str):
    # Minimal horoscope-like object for calculate_porutham
    return type(
        "H",
        (),
        {
            "nakshatra": nak,
            "rasi": _nak_rasi(nak),
            "gana": NAKSHATRA_MAP[nak].get("gana", ""),
            "yoni": NAKSHATRA_MAP[nak].get("yoni", ""),
            "rajju": NAKSHATRA_MAP[nak].get("rajju", ""),
        },
    )()


def main() -> None:
    out: dict[str, dict] = {}
    totals: list[float] = []
    rajju_dosha = 0
    koota_keys = [
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
    ]
    koota_zero_counts = {k: 0 for k in koota_keys}

    for b in NAKSHATRA_ORDER:
        for g in NAKSHATRA_ORDER:
            key = f"{b}_{g}".replace(" ", "_")
            bride = _h(b)
            groom = _h(g)
            r = calculate_porutham(bride, groom)
            kp = r["koota_points"]
            total = float(r["score"])
            totals.append(total)
            if kp.get("rajju") == 0.0:
                rajju_dosha += 1
            for kk in koota_keys:
                if kp.get(kk) == 0.0:
                    koota_zero_counts[kk] += 1

            out[key] = {
                "bride": b,
                "groom": g,
                "bride_rasi": bride.rasi,
                "groom_rasi": groom.rasi,
                **{k: float(kp.get(k, 0.0)) for k in koota_keys},
                "total": total,
            }

    p = Path(__file__).resolve().parent / "computed_729.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    bins = [(0, 2), (2, 4), (4, 6), (6, 8), (8, 10.01)]
    bin_counts = {f"{a}-{b}": 0 for a, b in bins}
    for t in totals:
        for a, b in bins:
            if a <= t < b:
                bin_counts[f"{a}-{b}"] += 1
                break

    print("Wrote", p, "pairs=", len(out))
    print("Total score distribution:", bin_counts)
    print("Rajju dosha count:", rajju_dosha)
    print("Zero counts per koota:", koota_zero_counts)


if __name__ == "__main__":
    main()

