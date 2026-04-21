#!/usr/bin/env python3
"""
Fetch 89 strategic nakshatra-porutham pairs from Prokerala API (basic endpoint).

Basic responses omit per-koota ``points``; only ``has_porutham`` booleans are returned.
Those are mapped to 1.0 / 0.0 (half-point scores from the advanced API are not available
at this URL).

Run from repository root:
  python scripts/fetch_strategic_pairs.py

Resume: progress is saved after each pair to astrology/tests/strategic_progress.json.
Override credentials with PROKERALA_CLIENT_ID / PROKERALA_CLIENT_SECRET env vars.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CLIENT_ID = os.environ.get(
    "PROKERALA_CLIENT_ID",
    "27ab4829-8315-46fd-aceb-f3c22adaff4c",
)
CLIENT_SECRET = os.environ.get(
    "PROKERALA_CLIENT_SECRET",
    "qxOKRnNCOtalYFSq7mpCtVFH1InxoxAqCKeuNQx7",
)

OUTPUT_FILE = REPO_ROOT / "astrology" / "tests" / "ground_truth_strategic.json"
PROGRESS_FILE = REPO_ROOT / "astrology" / "tests" / "strategic_progress.json"

TOKEN_URL = "https://api.prokerala.com/token"
API_URL = "https://api.prokerala.com/v2/astrology/nakshatra-porutham"

NAKSHATRAS = [
    "Ashwini",
    "Bharani",
    "Krittika",
    "Rohini",
    "Mrigashirsha",
    "Ardra",
    "Punarvasu",
    "Pushya",
    "Ashlesha",
    "Magha",
    "Purva Phalguni",
    "Uttara Phalguni",
    "Hasta",
    "Chitra",
    "Swati",
    "Vishakha",
    "Anuradha",
    "Jyeshtha",
    "Mula",
    "Purva Ashadha",
    "Uttara Ashadha",
    "Shravana",
    "Dhanishta",
    "Shatabhisha",
    "Purva Bhadrapada",
    "Uttara Bhadrapada",
    "Revati",
]

NAK_INDEX = {n: i for i, n in enumerate(NAKSHATRAS)}

# Prokerala JSON uses English names; aliases cover minor spelling variants.
KOOTA_NAME_MAP = {
    "Dina Porutham": "dina",
    "Gana Porutham": "gana",
    "Mahendra Porutham": "mahendra",
    "Stree Deergha Porutham": "sthree_deergha",
    "Yoni Porutham": "yoni",
    "Veda Porutham": "vedha",
    "Rajju Porutham": "rajju",
    "Rasi Porutham": "rasi",
    "Rasiyathipathi Porutham": "rasi_adhipathi",
    "Rasi Lord Porutham": "rasi_adhipathi",
    "Vasya Porutham": "vasya",
    "Vashya Porutham": "vasya",
}

# (bride_nakshatra, groom_nakshatra, reason) — 89 pairs total
STRATEGIC_PAIRS: list[tuple[str, str, str]] = [
    # RAJJU (15)
    ("Ashwini", "Magha", "Rajju Pada+Pada=0"),
    ("Ashwini", "Revati", "Rajju Pada+Pada=0"),
    ("Bharani", "Pushya", "Rajju Kati+Kati=0"),
    ("Bharani", "Chitra", "Rajju Kati+Kati=0 Chitra fix"),
    ("Bharani", "Dhanishta", "Rajju Kati+Kati=0 Dhanishta fix"),
    ("Chitra", "Dhanishta", "Rajju Kati+Kati=0"),
    ("Krittika", "Vishakha", "Rajju Nabhi+Nabhi=0"),
    ("Rohini", "Hasta", "Rajju Kanta+Kanta=0"),
    ("Rohini", "Shravana", "Rajju Kanta+Kanta=0"),
    ("Ashwini", "Bharani", "Rajju Pada+Kati=1"),
    ("Mrigashirsha", "Chitra", "Rajju Sira+Kati=1"),
    ("Mrigashirsha", "Dhanishta", "Rajju Sira+Kati=1"),
    ("Mrigashirsha", "Pushya", "Rajju Sira+Kati=1"),
    ("Rohini", "Bharani", "Rajju Kanta+Kati=1"),
    ("Krittika", "Ashwini", "Rajju Nabhi+Pada=1"),
    # YONI (17)
    ("Shatabhisha", "Ashwini", "Yoni Horse F+M=1.0 natural"),
    ("Revati", "Bharani", "Yoni Elephant F+M=1.0 natural"),
    ("Chitra", "Vishakha", "Yoni Tiger F+M=1.0 natural"),
    ("Purva Phalguni", "Magha", "Yoni Rat F+M=1.0 natural"),
    ("Mrigashirsha", "Rohini", "Yoni Serpent F+M=1.0 natural"),
    ("Ashwini", "Shatabhisha", "Yoni Horse M+F=0 Vikara"),
    ("Bharani", "Revati", "Yoni Elephant M+F=0 Vikara"),
    ("Vishakha", "Chitra", "Yoni Tiger M+F=0 Vikara"),
    ("Pushya", "Chitra", "Yoni Sheep/M+Tiger/F=0 cross-animal Vikara"),
    ("Bharani", "Ardra", "Yoni Elephant/M+Dog/F=0 cross-animal Vikara"),
    ("Hasta", "Swati", "Yoni Buffalo M+F=0 Vikara"),
    ("Ashwini", "Hasta", "Yoni Horse+Buffalo=enemy=0"),
    ("Magha", "Ashlesha", "Yoni Rat+Cat=enemy=0"),
    ("Rohini", "Uttara Ashadha", "Yoni Serpent+Mongoose=enemy=0"),
    ("Mula", "Jyeshtha", "Yoni Dog+Deer=enemy=0"),
    ("Ashwini", "Rohini", "Yoni Horse+Serpent=0.5"),
    ("Bharani", "Pushya", "Yoni Elephant+Sheep=0.5"),
    # VEDHA (16)
    ("Ashwini", "Jyeshtha", "Vedha pair=0"),
    ("Bharani", "Anuradha", "Vedha pair=0"),
    ("Krittika", "Vishakha", "Vedha pair=0"),
    ("Rohini", "Swati", "Vedha pair=0"),
    ("Mrigashirsha", "Chitra", "Vedha pair=0"),
    ("Ardra", "Hasta", "Vedha pair=0"),
    ("Punarvasu", "Uttara Phalguni", "Vedha pair=0"),
    ("Pushya", "Purva Phalguni", "Vedha pair=0"),
    ("Ashlesha", "Magha", "Vedha pair=0"),
    ("Mula", "Revati", "Vedha pair=0"),
    ("Purva Ashadha", "Uttara Bhadrapada", "Vedha pair=0"),
    ("Uttara Ashadha", "Purva Bhadrapada", "Vedha pair=0"),
    ("Shravana", "Shatabhisha", "Vedha pair=0"),
    ("Dhanishta", "Chitra", "Vedha pair=0 Bug16 fix"),
    ("Ashwini", "Bharani", "Vedha non-pair=1"),
    ("Shravana", "Chitra", "Vedha non-pair=1"),
    # VASYA (14)
    ("Ashwini", "Vishakha", "Vasya Mesha/Vrischika=1"),
    ("Ashwini", "Dhanishta", "Vasya Mesha/Kumbha=1 Bug21"),
    ("Krittika", "Punarvasu", "Vasya Vrishabha/Karka=1"),
    ("Krittika", "Chitra", "Vasya Vrishabha/Tula=1"),
    ("Mrigashirsha", "Uttara Phalguni", "Vasya Mithuna/Kanya=1"),
    ("Punarvasu", "Vishakha", "Vasya Karka/Vrischika=1"),
    ("Chitra", "Uttara Ashadha", "Vasya Tula/Makara=1 confirmed"),
    ("Mula", "Purva Bhadrapada", "Vasya Dhanus/Meena=1"),
    ("Uttara Ashadha", "Ashwini", "Vasya Makara/Mesha=1"),
    ("Uttara Ashadha", "Dhanishta", "Vasya Makara/Kumbha=1"),
    ("Purva Bhadrapada", "Mrigashirsha", "Vasya Meena/Mithuna=1"),
    ("Purva Bhadrapada", "Punarvasu", "Vasya Meena/Karka=1"),
    ("Ashwini", "Mrigashirsha", "Vasya Mesha/Mithuna=0 non-pair"),
    ("Magha", "Dhanishta", "Vasya Simha/Kumbha=0 non-pair"),
    # DINA (8)
    ("Ashwini", "Bharani", "Dina count=2 good"),
    ("Ashwini", "Rohini", "Dina count=4 good"),
    ("Ashwini", "Ardra", "Dina count=7 bad"),
    ("Ashwini", "Ashlesha", "Dina count=9 good"),
    ("Dhanishta", "Chitra", "Dina count=19 good Bug18"),
    ("Revati", "Ashwini", "Dina wrap-around count=2 good"),
    ("Ashwini", "Ashwini", "Dina same nak count=1 bad"),
    ("Ashwini", "Krittika", "Dina count=3 bad"),
    # GANA (9)
    ("Ashwini", "Krittika", "Gana Deva+Deva=1"),
    ("Bharani", "Rohini", "Gana Manushya+Manushya=1"),
    ("Ardra", "Ashlesha", "Gana Rakshasa+Rakshasa=1"),
    ("Ashwini", "Bharani", "Gana Deva+Manushya=0.5"),
    ("Bharani", "Ashwini", "Gana Manushya+Deva=0.5"),
    ("Bharani", "Ardra", "Gana Manushya+Rakshasa=0.5"),
    ("Ardra", "Bharani", "Gana Rakshasa+Manushya=0.5"),
    ("Ashwini", "Ardra", "Gana Deva+Rakshasa=0"),
    ("Ardra", "Ashwini", "Gana Rakshasa+Deva=0"),
    # RASYADHIPATHI (10)
    ("Uttara Ashadha", "Chitra", "Rasy Saturn/Venus groom→Saturn=friend=1"),
    ("Punarvasu", "Chitra", "Rasy Moon/Venus groom→Moon=enemy=0"),
    ("Ashwini", "Dhanishta", "Rasy Mars/Saturn groom→Mars=enemy=0"),
    ("Ashwini", "Mrigashirsha", "Rasy Mars/Mercury groom→Mars=neutral=1"),
    ("Magha", "Ashwini", "Rasy Sun/Mars groom→Sun=friend=1"),
    ("Ashwini", "Magha", "Rasy Mars/Sun groom→Mars=friend=1"),
    ("Mrigashirsha", "Mrigashirsha", "Rasy Mercury/Mercury same=1"),
    ("Mula", "Purva Bhadrapada", "Rasy Jupiter/Jupiter same=1"),
    ("Uttara Ashadha", "Dhanishta", "Rasy Saturn/Saturn same=1"),
    ("Ashwini", "Krittika", "Rasy Mars/Sun groom→Mars=friend=1"),
]


def _nak_index(name: str) -> int:
    if name not in NAK_INDEX:
        raise ValueError(f"Unknown nakshatra: {name!r}")
    return NAK_INDEX[name]


def _fetch_token() -> str:
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    token = payload.get("access_token")
    if not token:
        raise RuntimeError(f"No access_token in token response: {payload}")
    return str(token)


def _parse_koota_points(matches: list) -> dict[str, float]:
    out: dict[str, float] = {}
    for m in matches:
        raw_name = m.get("name") or ""
        key = KOOTA_NAME_MAP.get(raw_name.strip())
        if not key:
            continue
        pts = m.get("points")
        if pts is not None:
            out[key] = float(pts)
        elif "has_porutham" in m:
            # Basic endpoint: boolean only (no fractional scores).
            out[key] = 1.0 if m["has_porutham"] else 0.0
        else:
            raise ValueError(f"Missing points and has_porutham for match {raw_name!r}: {m}")
    expected_keys = set(KOOTA_NAME_MAP.values())
    missing = expected_keys - set(out.keys())
    if missing:
        raise ValueError(f"Incomplete koota parse, missing: {sorted(missing)} from {matches}")
    return out


def _fetch_pair(token: str, bride: str, groom: str, pada: int = 1) -> dict:
    girl_id = _nak_index(bride)
    boy_id = _nak_index(groom)
    q = urllib.parse.urlencode(
        {
            "girl_nakshatra": girl_id,
            "girl_nakshatra_pada": pada,
            "boy_nakshatra": boy_id,
            "boy_nakshatra_pada": pada,
        }
    )
    url = f"{API_URL}?{q}"
    ctx = ssl.create_default_context()
    body: dict | None = None
    for attempt in range(6):
        req = urllib.request.Request(
            url,
            method="GET",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and attempt < 5:
                wait = 65
                print(f"  rate limited (429), sleeping {wait}s then retry ...")
                time.sleep(wait)
                continue
            hint = ""
            if exc.code == 403 and "credit" in detail.lower():
                hint = (
                    "Prokerala returned insufficient credit balance; add credits in the "
                    "dashboard, wait for quota reset, then rerun the script (it resumes from "
                    f"{PROGRESS_FILE.name}).\n"
                )
            elif exc.code == 400 and "sandbox" in detail.lower():
                hint = (
                    "Sandbox mode only allows Ashwini (nakshatra id 0); disable sandbox or use "
                    "live credentials.\n"
                )
            elif exc.code == 429:
                hint = "Rate limit: wait and rerun; progress is saved after each pair.\n"
            raise RuntimeError(
                f"HTTP {exc.code} from Prokerala API for {url}\n{detail}\n{hint}"
            ) from exc
    assert body is not None
    if body.get("status") != "ok":
        raise RuntimeError(f"API error: {body}")
    data = body.get("data") or {}
    matches = data.get("matches") or []
    koota = _parse_koota_points(matches)
    total = float(data.get("obtained_points", round(sum(koota.values()), 2)))
    return {
        "bride_nakshatra": bride,
        "groom_nakshatra": groom,
        "girl_nakshatra_id": girl_id,
        "boy_nakshatra_id": boy_id,
        "koota_points": koota,
        "total": total,
        "maximum_points": float(data.get("maximum_points", 10)),
    }


def _load_progress() -> tuple[int, list[dict]]:
    if not PROGRESS_FILE.exists():
        return 0, []
    raw = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return int(raw.get("next_index", 0)), list(raw.get("results", []))


def _save_progress(next_index: int, results: list[dict]) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(
        json.dumps({"next_index": next_index, "results": results}, indent=2),
        encoding="utf-8",
    )


def _save_output(results: list[dict]) -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "source": "Prokerala API v2 /astrology/nakshatra-porutham (basic)",
        "pair_count": len(results),
        "pairs": results,
    }
    OUTPUT_FILE.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


def fetch_pair(token: str, bride_idx: int, groom_idx: int, *, pada: int = 1) -> dict[str, float]:
    """Return koota_points for girl=NAKSHATRAS[bride_idx], boy=NAKSHATRAS[groom_idx]."""
    row = _fetch_pair(token, NAKSHATRAS[bride_idx], NAKSHATRAS[groom_idx], pada=pada)
    return row["koota_points"]


def main() -> None:
    if len(STRATEGIC_PAIRS) != 89:
        raise SystemExit(f"STRATEGIC_PAIRS must be 89 entries, got {len(STRATEGIC_PAIRS)}")

    next_index, results = _load_progress()
    if next_index >= len(STRATEGIC_PAIRS) and results:
        print(f"Already complete ({len(results)} pairs). Delete {PROGRESS_FILE} to refetch.")
        _save_output(results)
        return

    token = _fetch_token()
    print(f"Token OK. Resuming from pair index {next_index}/{len(STRATEGIC_PAIRS)}")

    # Sanity check — verify Production mode with known pair
    # Vishakha(15 bride) + Chitra(13 groom)
    # Yoni MUST be 0.0 in Production mode
    # In Sandbox mode it returns fixed demo data (0.5 or 1.0)
    print("Running Production sanity check...")
    test_scores = fetch_pair(token, 15, 13)
    yoni_val = test_scores.get("yoni", -1) if test_scores else -1
    if abs(float(yoni_val) - 0.0) > 0.001:
        print(f"SANITY CHECK FAILED: Yoni={yoni_val} expected=0.0")
        print("API is returning sandbox/demo data. Check environment setting.")
        print("Go to https://api.prokerala.com/account → App IDs → Environment: Production")
        sys.exit(1)
    print(f"Sanity check PASSED: Yoni={yoni_val} — Production mode confirmed")
    print()

    remaining = len(STRATEGIC_PAIRS) - next_index
    est_min = max(1, int((remaining * 12) / 60))
    print(f"Starting fetch — {remaining} pairs remaining")
    print(f"Rate: 5 req/min (free plan) = ~{est_min} min remaining")
    print()

    for idx in range(next_index, len(STRATEGIC_PAIRS)):
        bride, groom, reason = STRATEGIC_PAIRS[idx]
        print(f"[{idx + 1}/89] {bride} / {groom} ...")
        row = _fetch_pair(token, bride, groom)
        row["reason"] = reason
        results.append(row)
        _save_progress(idx + 1, results)
        _save_output(results)
        if (idx + 1) % 5 == 0 or (idx + 1) == len(STRATEGIC_PAIRS):
            print(f"  checkpoint -> {OUTPUT_FILE.name} ({len(results)} pairs)")

        # Prokerala: 5 requests / 60s; 12s spacing stays under limit with margin.
        if idx + 1 < len(STRATEGIC_PAIRS):
            time.sleep(12)

    print(f"Done. {len(results)} pairs saved.")


if __name__ == "__main__":
    main()
