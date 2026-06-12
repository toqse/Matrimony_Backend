"""
Horoscope Matching Report PDF — Kerala-style 3-page compatibility document.

Rendered with ReportLab via the framework-agnostic renderer in
``horoscope_report.py`` (repo root). This module is the Django adapter: it maps
``HoroscopeProfile`` / porutham data into the renderer's plain-dict contract.
The same ``generate_match_report_pdf`` is used by the user site
(``astrology.views.MatchReportMeView``) and the admin/staff/branch panels
(``admin_panel.horoscope_mgmt``), so both surfaces share one report.
"""
from __future__ import annotations

import sys
from typing import Any

from django.conf import settings
from django.utils import timezone

from astrology.charts import (
    dasa_lord,
    format_dasa_balance,
    lagnam_name,
    moon_rasi_name,
    star_name,
)
from astrology.porutham import calculate_porutham

# key (porutham result) -> (English label, one-line significance)
PORUTHAM_ROWS: tuple[tuple[str, str, str], ...] = (
    ('dinam', 'Dinam', 'Health & longevity'),
    ('ganam', 'Ganam', 'Temperament & nature'),
    ('mahendra', 'Mahendram', 'Prosperity & progeny'),
    ('sthree_deerga', 'Sthree Deergham', 'Long married life'),
    ('yoni', 'Yoni', 'Physical compatibility'),
    ('rasi', 'Rasi', 'Mental harmony'),
    ('rasyadhipam', 'Rasyadhipathi', 'Ruling lords match'),
    ('vasyam', 'Vasyam', 'Mutual attraction'),
    ('rajju_dosham', 'Rajju', 'Life span protection'),
    ('vedha_dosham', 'Vedha', 'Absence of affliction'),
)


def _import_renderer():
    """Import the repo-root ``horoscope_report`` renderer, fixing sys.path."""
    try:
        import horoscope_report  # noqa: WPS433
    except ImportError:
        base = str(getattr(settings, 'BASE_DIR', '') or '')
        if base and base not in sys.path:
            sys.path.insert(0, base)
        import horoscope_report  # noqa: WPS433
    return horoscope_report


def _person_dict(hp, user, role: str) -> dict[str, Any]:
    name = (hp.pr_name or getattr(user, 'name', '') or '').strip()
    balance = format_dasa_balance(hp.pr_dasabalance)
    horoscope_report = _import_renderer()
    return {
        'role': role,
        'name': name,
        'am_id': getattr(user, 'matri_id', '') or '',
        'nakshatra': hp.star_name or star_name(hp.pr_star) or '\u2014',
        'padam': hp.pr_pada if hp.pr_pada else '\u2014',
        'rasi': hp.rasi_sign or moon_rasi_name(hp.pr_rasi) or '\u2014',
        'lagnam': hp.lagnam or lagnam_name(hp.pr_rasi) or '\u2014',
        'dasa': balance.get('balance_text', '') or '\u2014',
        'lord': dasa_lord(hp.pr_star) or '\u2014',
        'placements': horoscope_report.placements_from_pr_rasi(hp.pr_rasi),
        'amsa_placements': horoscope_report.placements_from_pr_rasi(
            getattr(hp, 'pr_amsa', '') or ''
        ),
        'bhava_placements': horoscope_report.placements_from_pr_rasi(
            getattr(hp, 'pr_bhav', '') or ''
        ),
    }


def build_match_report_context(
    bride_hp,
    groom_hp,
    bride_user,
    groom_user,
    bride_photo=None,  # kept for signature compatibility; unused by ReportLab.
    groom_photo=None,
) -> dict[str, Any]:
    porutham = calculate_porutham(bride_hp, groom_hp)
    poruthams = porutham.get('poruthams') or {}
    max_score = int(porutham.get('max_score') or 10)
    matched_count = sum(1 for _key, _label, _sig in PORUTHAM_ROWS if poruthams.get(_key))
    unmatched_count = max_score - matched_count

    rows = [
        {
            'english': label,
            'significance': significance,
            'matched': bool(poruthams.get(key)),
        }
        for key, label, significance in PORUTHAM_ROWS
    ]

    bride_name = (bride_hp.pr_name or bride_user.name or '').strip()
    groom_name = (groom_hp.pr_name or groom_user.name or '').strip()
    generated_at = timezone.localtime(timezone.now())

    return {
        'couple': f'{bride_name} & {groom_name}'.strip(' &'),
        'date': generated_at.strftime('%d-%m-%Y %H:%M'),
        'score': matched_count,
        'max': max_score,
        'overall': porutham.get('overall_result') or porutham.get('result') or '',
        'matched': matched_count,
        'unmatched': unmatched_count,
        'rows': rows,
        'bride': _person_dict(bride_hp, bride_user, 'BRIDE'),
        'groom': _person_dict(groom_hp, groom_user, 'GROOM'),
    }


def generate_match_report_pdf(
    bride_hp,
    groom_hp,
    bride_user,
    groom_user,
    bride_photo=None,
    groom_photo=None,
) -> tuple[bytes, str]:
    report = build_match_report_context(
        bride_hp,
        groom_hp,
        bride_user,
        groom_user,
    )
    horoscope_report = _import_renderer()
    return horoscope_report.build_horoscope_report_pdf(report), 'pdf'
