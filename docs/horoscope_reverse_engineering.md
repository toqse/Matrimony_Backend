# Horoscope Decoder Reverse Engineering & Verification Report

Goal: make Django's decoded Rasi / Amsakom / Bhavom charts match the Windows
Horoscope Generator EXE exactly (100% house-by-house) before any further UI work.

This document is the verification report and reverse-engineering record. It does
NOT modify the UI or chart components.

---

## 1. Executive summary

- The database strings are correct (e.g. `pr_rasi = AGEEHKGAEKJ`). The dispute is
  only about how those strings are decoded into per-house planet placements.
- The decode pipeline already exists and is centralized:
  `astrology/charts.py` (`PLANETS`, `decode_chart`) ->
  `astrology/services/horoscope_decoder.py` -> verification in
  `astrology/services/horoscope_verification.py`.
- 7 of 11 planet positions are PROVEN from existing code (`calc_papatha`,
  `mark_horoscope_done`) plus the Rahu/Ketu opposition. Three positions
  (indices 4, 5, 10) are ASSUMED, not proven. These are the prime suspects.
- BLOCKER: the current verification reports "100%" only because the ground-truth
  fixture's `exe` side is pre-filled with Django's own decode
  (`verified_against_exe: false`). It is a self-comparison and certifies nothing.
  Real certification needs the EXE's own house output for at least one record.

---

## 2. Codebase search: `pr_rasi` / `pr_amsa` / `pr_bhav`

Files that reference the three chart strings:

| File | Role |
|------|------|
| `astrology/models.py` | `HoroscopeProfile` fields `pr_rasi/pr_amsa/pr_bhav` (EXE bridge) |
| `astrology/migrations/0007_replace_horoscope_with_exe_bridge.py` | Column definitions |
| `astrology/porutham.py` | `chart_to_array` (char->sign), `calc_papatha` (proves planet indices) |
| `astrology/charts.py` | `PLANETS` table + `decode_chart` (the single decode source of truth) |
| `astrology/services/horoscope_decoder.py` | `decode_rasi/amsa/bhava`, `decode_detailed`, `decode_bundle` |
| `astrology/services/horoscope_verification.py` | House-by-house EXE vs Django comparison |
| `astrology/management/commands/verify_horoscope_decoder.py` | CLI verification + accuracy |
| `astrology/management/commands/mark_horoscope_done.py` | Reads index 0 (lagnam) and 2 (rasi_sign) |
| `astrology/serializers.py` | Serializes `charts` via `build_horoscope_charts` |
| `astrology/views.py` | `HoroscopeDecoderDebugView` -> `GET /api/horoscope/debug/<id>/` |
| `astrology/fixtures/horoscope_exe_ground_truth.json` | Ground-truth fixture (EXE side) |
| `astrology/tests/test_charts.py`, `astrology/tests/test_horoscope_decoder.py` | Tests |
| `profiles/legacy_import/horoscope.py`, `profiles/legacy_import/importer.py` | Legacy import writes these |
| `admin_panel/horoscope_mgmt/...` | Panel read/manage |

---

## 3. Encoding / decoding logic

### 3.1 String format

Each chart string is exactly 11 characters, `A`-`L`.
**Position = a fixed planet. Character = the zodiac sign that planet sits in.**

### 3.2 Character -> zodiac sign (PROVEN)

`A`=1, `B`=2, ... `L`=12, via `astrology/porutham.py::chart_to_array`:

```python
def chart_to_array(s):
    if not s or len(s) < 11:
        return []
    return [ord(c) - ord('A') + 1 for c in s[:11]]
```

Sign numbers -> Kerala rasi names via `RASI_NAMES`:

| # | Rasi | # | Rasi | # | Rasi |
|---|------|---|------|---|------|
| 1 | Medam | 5 | Chingam | 9 | Dhanu |
| 2 | Edavam | 6 | Kanni | 10 | Makaram |
| 3 | Midhunam | 7 | Thulam | 11 | Kumbham |
| 4 | Kadakam | 8 | Vrischikam | 12 | Meenam |

### 3.3 Position -> planet (the mapping under test)

| Index | Planet | Abbr | Status | Evidence |
|-------|--------|------|--------|----------|
| 0 | Lagnam | La | PROVEN | `calc_papatha` ref `plan_nos[0]`; `mark_horoscope_done` reads idx 0 as lagnam |
| 1 | Sun | Su | PROVEN | `calc_papatha` malefic `papacode` 0-based idx 1 |
| 2 | Moon | Mo | PROVEN | `calc_papatha` ref `plan_nos[1]`; `mark_horoscope_done` reads idx 2 as rasi_sign |
| 3 | Mars | Ma | PROVEN | `calc_papatha` malefic idx 3 |
| 4 | Mercury | Me | **ASSUMED** | "classic graha order" only; not referenced by any calc |
| 5 | Jupiter | Ju | **ASSUMED** | "classic graha order" only; not referenced by any calc |
| 6 | Venus | Ve | PROVEN | `calc_papatha` ref `plan_nos[2]` |
| 7 | Saturn | Sa | PROVEN | `calc_papatha` malefic idx 7 |
| 8 | Rahu | Ra | PROVEN | `calc_papatha` malefic idx 8 |
| 9 | Ketu | Ke | PROVEN | always 6 signs opposite Rahu (enforced by test_charts) |
| 10 | Maandi (Gulika) | Md | **ASSUMED** | last remaining slot only |

How `calc_papatha` fixes 0,1,2,3,6,7,8:

```python
plan_nos = [0, 2, 6]      # papasamyam reference bodies: Lagna, Moon, Venus
papacode = [9, 2, 8, 4]   # 1-based -> 0-based [8,1,7,3] = Rahu, Sun, Saturn, Mars
```

### 3.4 Suspected mapping errors (where EXE mismatch will come from)

Only three positions are unproven; any EXE mismatch must originate here:

1. **Mercury vs Jupiter (index 4 vs 5)** — PRIME SUSPECT. If the EXE writes
   Jupiter before Mercury, every chart where Mercury and Jupiter sit in different
   signs will show them swapped between two houses.
2. **Maandi at index 10** — needs confirmation that slot 10 is Maandi/Gulika and
   not some other point (or absent).
3. Indirectly, if 4/5 are wrong, the "Mercury"/"Jupiter" labels in the report
   below are what will flip.

Rahu/Ketu opposition holds for the example (`AGEEHKGAEKJ`: Rahu idx8 = E = 5,
Ketu idx9 = K = 11, and 5 + 6 = 11), so index 9 = Ketu is safe.

---

## 4. House mapping (chart layout)

Decoded output is keyed by **zodiac sign number (1-12)**, not visual grid cell.
The South Indian fixed-sign grid mapping lives in
`astrology/services/chart_malayalam_data.py::RASI_TO_GRID` and
`templates/astrology/components/south_indian_chart.html`. This is presentation
only and is out of scope (no UI changes).

---

## 5. Worked example: the reported strings

Decoded by Django today (via `decode_bundle`):

### RASI `AGEEHKGAEKJ`

| House (sign) | Django |
|---|---|
| 1 Medam | La, Sa |
| 5 Chingam | Mo, Ma, Ra |
| 7 Thulam | Su, Ve |
| 8 Vrischikam | Me |
| 10 Makaram | Md |
| 11 Kumbham | Ju, Ke |

(houses 2,3,4,6,9,12 empty)

### AMSA `EBAIIBCBAGA`

| House (sign) | Django |
|---|---|
| 1 Medam | Mo, Ra, Md |
| 2 Edavam | Su, Ju, Sa |
| 3 Midhunam | Ve |
| 5 Chingam | La |
| 7 Thulam | Ke |
| 9 Dhanu | Ma, Me |

### BHAVA `AGEFHKHAEKJ`

| House (sign) | Django |
|---|---|
| 1 Medam | La, Sa |
| 5 Chingam | Mo, Ra |
| 6 Kanni | Ma |
| 7 Thulam | Su |
| 8 Vrischikam | Me, Ve |
| 10 Makaram | Md |
| 11 Kumbham | Ju, Ke |

If the EXE shows Mercury and Jupiter in different houses than above, that
confirms the index 4/5 swap.

---

## 6. Verification report format (EXE vs Django, house-by-house)

Produced by `python manage.py verify_horoscope_decoder`. Example of a FAIL line:

```
House  1  EXE: ['La', 'Sa']  Django: ['La', 'Ju']  Status: FAIL
```

`render_report` only prints houses that differ, plus per-chart accuracy and an
overall accuracy percentage. `--strict` exits non-zero below 100%.

### Current status

```
verified_against_exe = false
OVERALL DECODER ACCURACY: 100.00%   <-- NOT MEANINGFUL (self-comparison)
```

The fixture's `exe` houses are currently Django's own decode, so the 100% does
NOT certify EXE parity. Mismatches cannot be enumerated until the EXE side is
filled with real output.

---

## 7. How to reach (and certify) 100%

1. Open a known record in the Windows Horoscope Generator (e.g. JOSEPH id 1842,
   or the example `AGEEHKGAEKJ`).
2. For each chart (Rasi, Amsakom, Bhavom), read the planets in each of the 12
   houses and write them into the matching record's `exe.rasi/amsa/bhava` in
   `astrology/fixtures/horoscope_exe_ground_truth.json`.
3. Set `"verified_against_exe": true`.
4. Run:

   ```
   python manage.py verify_horoscope_decoder --strict
   ```

5. Read the FAIL lines. If Mercury/Jupiter appear swapped between two houses,
   swap indices 4 and 5 in `astrology/charts.py::PLANETS` (the single source of
   truth) and re-run. Repeat for Maandi (index 10) if it disagrees.
6. Decoder is certified when the tool prints `OVERALL DECODER ACCURACY: 100.00%`
   with `verified_against_exe: true`.

Note: the fix point for any mapping correction is the single `PLANETS` list in
`astrology/charts.py`. No UI or chart component needs to change for a decode fix.

---

## 8. Debug helper

`astrology/services/horoscope_decoder.py::decode_bundle(raw_rasi, raw_amsa,
raw_bhava, verbose=True)` returns:

```json
{
  "raw_rasi": "...", "raw_amsa": "...", "raw_bhava": "...",
  "decoded_rasi": {"1": ["La", "Sa"], ...},
  "decoded_amsa": {...},
  "decoded_bhava": {...},
  "detail": { "rasi": {planet->sign...}, "amsa": {...}, "bhava": {...} }
}
```

Live endpoint: `GET /api/horoscope/debug/<id>/` returns the same raw + decoded
shape for a stored record.
