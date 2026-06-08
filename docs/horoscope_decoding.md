# Horoscope Decoding (Windows EXE Bridge)

How Django decodes the Windows Horoscope Generator output stored in the
`horoscope_profile` table. **No mapping in this document is guessed** - each one
cites the code or fact that establishes it.

## 1. Source fields

The EXE writes these columns on `horoscope_profile`:

| Field | Meaning | Format |
|-------|---------|--------|
| `pr_rasi` | Rasi chart | 11-char string `A`-`L` |
| `pr_amsa` | Amsakom (Navamsa) chart | 11-char string `A`-`L` |
| `pr_bhav` | Bhavom chart | 11-char string `A`-`L` |
| `pr_star` | Nakshatra number | int 1-27 |
| `pr_pada` | Nakshatra padam | int 1-4 |
| `pr_dasabalance` | Sishta dasa balance | int (days) |

Example (`id = 1842`, JOSEPH):

```
pr_rasi = BHEJGAFADJC
pr_amsa = DGDLBAFFGAL
pr_bhav = BHEJGLFADJC
pr_star = 10   pr_pada = 4   pr_dasabalance = 491
```

## 2. The 11-character string

Each of the three chart strings is exactly 11 characters. **Position = planet,
character = zodiac sign.**

### 2.1 Character -> zodiac sign

`A`=1, `B`=2, ... `L`=12 (`ord(c) - ord('A') + 1`).

Evidence: `astrology/porutham.py::chart_to_array` (existing, pre-dating this work):

```python
def chart_to_array(s):
    if not s or len(s) < 11:
        return []
    return [ord(c) - ord('A') + 1 for c in s[:11]]
```

Zodiac sign numbers map to Kerala rasi names via `RASI_NAMES` in the same file:

| # | Rasi (ML) | Western |
|---|-----------|---------|
| 1 | Medam | Mesha / Aries |
| 2 | Edavam | Vrishabha / Taurus |
| 3 | Midhunam | Mithuna / Gemini |
| 4 | Kadakam | Karka / Cancer |
| 5 | Chingam | Simha / Leo |
| 6 | Kanni | Kanya / Virgo |
| 7 | Thulam | Tula / Libra |
| 8 | Vrischikam | Vrischika / Scorpio |
| 9 | Dhanu | Dhanus / Sagittarius |
| 10 | Makaram | Makara / Capricorn |
| 11 | Kumbham | Kumbha / Aquarius |
| 12 | Meenam | Meena / Pisces |

### 2.2 Position -> planet

| Index | Planet | Abbr | Evidence |
|-------|--------|------|----------|
| 0 | Lagnam | La | `calc_papatha` reference point `plan_nos=[0,...]`; `mark_horoscope_done` reads index 0 as `lagnam` |
| 1 | Sun | Su | `calc_papatha` `papacode` malefic (0-based index 1) |
| 2 | Moon | Mo | `calc_papatha` reference point `plan_nos=[..,2,..]`; `mark_horoscope_done` reads index 2 as `rasi_sign` |
| 3 | Mars | Ma | `calc_papatha` `papacode` malefic (0-based index 3) |
| 4 | Mercury | Me | Classic graha order (Su, Mo, Ma, **Me**, Ju, Ve, Sa); only remaining slot |
| 5 | Jupiter | Ju | Classic graha order; only remaining slot |
| 6 | Venus | Ve | `calc_papatha` reference point `plan_nos=[..,..,6]` |
| 7 | Saturn | Sa | `calc_papatha` `papacode` malefic (0-based index 7) |
| 8 | Rahu | Ra | `calc_papatha` `papacode` malefic (0-based index 8); always 6 signs from Ketu |
| 9 | Ketu | Ke | Always 6 signs opposite Rahu in every chart string |
| 10 | Maandi (Gulika) | Md | Last slot; 11th body in Kerala charts after the 9 grahas + lagna |

#### How `calc_papatha` proves indices 0,1,2,3,6,7,8

From `astrology/porutham.py`:

```python
plan_nos = [0, 2, 6]          # papasamyam reference bodies: Lagna, Moon, Venus
papacode = [9, 2, 8, 4]       # 1-based -> 0-based [8, 1, 7, 3] = the four malefics
```

- `plan_nos = [0, 2, 6]` are the three points papasamyam (papa/dosha strength) is
  computed for in the Kerala system: **Lagna, Moon, Venus** -> indices 0, 2, 6.
- `papacode = [9, 2, 8, 4]` (1-based) -> 0-based `[8, 1, 7, 3]` are the natural
  malefics counted: **Rahu, Sun, Saturn, Mars** -> indices 8, 1, 7, 3.

Together these fix 0, 1, 2, 3, 6, 7, 8. Rahu/Ketu opposition fixes 9. The two
remaining slots (4, 5) take Mercury and Jupiter in the classic graha order, and
the final slot (10) is Maandi.

#### Rahu/Ketu opposition check

In every chart string, `(sign[9] - sign[8]) mod 12 == 6`. Verified for `id=1842`:

- rasi: Rahu=4 (Kadakam), Ketu=10 (Makaram) -> diff 6
- amsa: Rahu=7 (Thulam), Ketu=1 (Medam) -> diff 6
- bhava: Rahu=4 (Kadakam), Ketu=10 (Makaram) -> diff 6

This is enforced by `astrology/tests/test_charts.py::test_rahu_ketu_opposition`.

## 3. Lagna

`lagna_sign = sign(index 0)`. For `id=1842` rasi: index 0 = `B` = 2 = Edavam.
This matches `mark_horoscope_done` which already writes `hp.lagnam` from index 0.

## 4. House mapping (chart layout)

The decoder output is keyed by **zodiac sign number (1-12)**, not visual position.
The South Indian chart uses a fixed-sign perimeter (sign 12 top-left, clockwise).
Sign-number-to-grid mapping is documented in
`templates/astrology/components/south_indian_chart.html` and
`astrology/services/chart_malayalam_data.py::RASI_TO_GRID`.

Decoded `houses` dictionary: `{"1": [...], "2": [...], ..., "12": [...]}`, where
each list holds the planet abbreviations occupying that sign.

### Worked example: `pr_rasi = BHEJGAFADJC` (id 1842)

| Idx | Char | Sign | Rasi | Planet |
|-----|------|------|------|--------|
| 0 | B | 2 | Edavam | Lagnam (La) |
| 1 | H | 8 | Vrischikam | Sun (Su) |
| 2 | E | 5 | Chingam | Moon (Mo) |
| 3 | J | 10 | Makaram | Mars (Ma) |
| 4 | G | 7 | Thulam | Mercury (Me) |
| 5 | A | 1 | Medam | Jupiter (Ju) |
| 6 | F | 6 | Kanni | Venus (Ve) |
| 7 | A | 1 | Medam | Saturn (Sa) |
| 8 | D | 4 | Kadakam | Rahu (Ra) |
| 9 | J | 10 | Makaram | Ketu (Ke) |
| 10 | C | 3 | Midhunam | Maandi (Md) |

Resulting houses:

```
 1 Medam:      Ju, Sa
 2 Edavam:     La
 3 Midhunam:   Md
 4 Kadakam:    Ra
 5 Chingam:    Mo
 6 Kanni:      Ve
 7 Thulam:     Me
 8 Vrischikam: Su
 9 Dhanu:      (empty)
10 Makaram:    Ma, Ke
11 Kumbham:    (empty)
12 Meenam:     (empty)
```

## 5. Code map

| Concern | File |
|---------|------|
| Mapping tables (single source of truth) | `astrology/charts.py` (`PLANETS`, `decode_chart`) |
| Char->sign | `astrology/porutham.py::chart_to_array` |
| Decode API (`decode_rasi/amsa/bhava`) | `astrology/services/horoscope_decoder.py` |
| House-by-house comparison | `astrology/services/horoscope_verification.py` |
| Debug endpoint | `astrology/views.py::HoroscopeDecoderDebugView` -> `GET /api/horoscope/debug/<id>/` |
| Verification command | `astrology/management/commands/verify_horoscope_decoder.py` |
| EXE ground-truth fixture | `astrology/fixtures/horoscope_exe_ground_truth.json` |
| Tests | `astrology/tests/test_charts.py`, `astrology/tests/test_horoscope_decoder.py` |

## 6. Verifying against the EXE (100% accuracy procedure)

The codebase evidence above fixes the mapping, but **final certification that
Django reproduces the EXE exactly requires the EXE's own house output**, which
only the Windows tool can produce. To certify:

1. Open the record in the Windows Horoscope Generator (e.g. JOSEPH / id 1842).
2. For each chart (Rasi, Amsakom, Bhavom), read the planets in each of the 12
   houses and write them into `astrology/fixtures/horoscope_exe_ground_truth.json`
   under `exe.rasi`, `exe.amsa`, `exe.bhava`.
3. Set `"verified_against_exe": true`.
4. Run:

   ```
   python manage.py verify_horoscope_decoder --strict
   ```

5. The tool prints a house-by-house mismatch report and overall accuracy. A
   `FAIL` line shows `EXE: [...]` vs `Django: [...]` for any differing house.

Until step 3 is done, the fixture's `exe` values are a format template only
(pre-filled with Django's decode), and the tool prints a warning that the result
does not certify EXE parity.
