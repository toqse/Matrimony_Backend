"""
Horoscope decoder verification.

Compares the Windows EXE's house-by-house chart output against Django's
decode of the same raw string, producing a house-by-house mismatch report.

Ground truth (the EXE side) must be supplied externally; this module never
infers EXE output. It only compares two already-known house maps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from astrology.services.horoscope_decoder import (
    decode_amsa,
    decode_bhava,
    decode_rasi,
)

CHART_DECODERS = {
    'rasi': decode_rasi,
    'amsa': decode_amsa,
    'bhava': decode_bhava,
}


def _normalize_house_map(raw: dict | None) -> dict[str, list[str]]:
    """Coerce a house map into ``{"1".."12": sorted_list_of_abbr}`` for comparison."""
    out: dict[str, list[str]] = {str(h): [] for h in range(1, 13)}
    for key, value in (raw or {}).items():
        house = str(key).strip()
        if house not in out:
            continue
        if isinstance(value, str):
            items = [value] if value.strip() else []
        else:
            items = [str(v).strip() for v in (value or []) if str(v).strip()]
        out[house] = items
    return out


@dataclass
class HouseResult:
    house: str
    exe: list[str]
    django: list[str]

    @property
    def passed(self) -> bool:
        # Order-independent comparison: a house is a set of planets.
        return sorted(self.exe) == sorted(self.django)


@dataclass
class ChartResult:
    chart: str
    raw: str
    houses: list[HouseResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(h.passed for h in self.houses)

    @property
    def total(self) -> int:
        return len(self.houses)

    @property
    def matched(self) -> int:
        return sum(1 for h in self.houses if h.passed)

    @property
    def accuracy(self) -> float:
        return 100.0 * self.matched / self.total if self.total else 0.0


def compare_chart(chart: str, raw_string: str | None, exe_houses: dict | None) -> ChartResult:
    """Compare one chart (rasi/amsa/bhava) for a single record."""
    decoder = CHART_DECODERS[chart]
    django_houses = _normalize_house_map(decoder(raw_string))
    exe_norm = _normalize_house_map(exe_houses)

    result = ChartResult(chart=chart, raw=raw_string or '')
    for house in (str(h) for h in range(1, 13)):
        result.houses.append(
            HouseResult(
                house=house,
                exe=exe_norm[house],
                django=django_houses[house],
            )
        )
    return result


def verify_record(record: dict[str, Any]) -> dict[str, ChartResult]:
    """
    Verify one ground-truth record.

    ``record`` shape::

        {
          "id": 1842,
          "pr_rasi": "BHEJGAFADJC",
          "pr_amsa": "DGDLBAFFGAL",
          "pr_bhav": "BHEJGLFADJC",
          "exe": {
            "rasi":  {"1": ["Ju", "Sa"], ...},
            "amsa":  {...},
            "bhava": {...}
          }
        }
    """
    raw_keys = {'rasi': 'pr_rasi', 'amsa': 'pr_amsa', 'bhava': 'pr_bhav'}
    exe = record.get('exe') or {}
    results: dict[str, ChartResult] = {}
    for chart, raw_key in raw_keys.items():
        if chart not in exe:
            continue
        results[chart] = compare_chart(chart, record.get(raw_key), exe.get(chart))
    return results


def render_report(record_id: Any, results: dict[str, ChartResult]) -> str:
    """Human-readable house-by-house mismatch report for one record."""
    lines: list[str] = []
    lines.append(f'=== Horoscope id={record_id} ===')
    for chart, res in results.items():
        lines.append('')
        lines.append(
            f'[{chart.upper()}] raw={res.raw!r}  '
            f'accuracy={res.accuracy:.1f}%  ({res.matched}/{res.total})'
        )
        for h in res.houses:
            status = 'PASS' if h.passed else 'FAIL'
            if h.passed:
                continue
            lines.append(
                f'  House {h.house:>2}  EXE: {h.exe or "[]"}  '
                f'Django: {h.django or "[]"}  Status: {status}'
            )
        if res.passed:
            lines.append('  All 12 houses match.')
    return '\n'.join(lines)


def overall_accuracy(all_results: list[dict[str, ChartResult]]) -> float:
    total = 0
    matched = 0
    for results in all_results:
        for res in results.values():
            total += res.total
            matched += res.matched
    return 100.0 * matched / total if total else 0.0
