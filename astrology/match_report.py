"""
Horoscope Matching Report PDF — 3-page compatibility document.
Rendered via WeasyPrint (HTML/CSS), same stack as Jathagam / Thalakkuri.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from astrology.charts import (
    dasa_lord,
    format_dasa_balance,
    lagnam_name,
    moon_rasi_name,
    star_name,
)
from astrology.porutham import calculate_porutham
from astrology.thalakkuri_calc import build_chart_rows

PORUTHAM_ROWS: tuple[tuple[str, str], ...] = (
    ('dinam', 'Dinam'),
    ('ganam', 'Ganam'),
    ('mahendra', 'Mahendram'),
    ('sthree_deerga', 'Sthree Deergham'),
    ('yoni', 'Yoni'),
    ('rasi', 'Rasi'),
    ('rasyadhipam', 'Rasyadhipathi'),
    ('vasyam', 'Vasyam'),
    ('rajju_dosham', 'Rajju'),
    ('vedha_dosham', 'Vedha'),
)


def _score_color(score: int) -> str:
    if score <= 3:
        return '#c0392b'
    if score <= 6:
        return '#e67e22'
    if score <= 8:
        return '#1e8449'
    return '#0b5d1e'


def _photo_uri(photo_field) -> str | None:
    if not photo_field or not getattr(photo_field, 'name', None):
        return None
    try:
        path = photo_field.path
    except (ValueError, AttributeError):
        return None
    if path and os.path.exists(path):
        return Path(path).as_uri()
    return None


def _person_dict(hp, user, photo_field) -> dict[str, Any]:
    name = (hp.pr_name or getattr(user, 'name', '') or '').strip()
    balance = format_dasa_balance(hp.pr_dasabalance)
    return {
        'name': name,
        'matri_id': getattr(user, 'matri_id', '') or '',
        'initial': (name[0] if name else '?').upper(),
        'photo_uri': _photo_uri(photo_field),
        'nakshatra': hp.star_name or star_name(hp.pr_star),
        'padam': hp.pr_pada if hp.pr_pada else '—',
        'rasi': hp.rasi_sign or moon_rasi_name(hp.pr_rasi),
        'lagnam': hp.lagnam or lagnam_name(hp.pr_rasi),
        'dasa_balance': balance.get('balance_text', '') or '—',
        'dasa_lord': dasa_lord(hp.pr_star) or '—',
        'rasi_rows': build_chart_rows(hp.pr_rasi),
    }


def build_match_report_context(
    bride_hp,
    groom_hp,
    bride_user,
    groom_user,
    bride_photo=None,
    groom_photo=None,
) -> dict[str, Any]:
    porutham = calculate_porutham(bride_hp, groom_hp)
    poruthams = porutham.get('poruthams') or {}
    score = int(porutham.get('score') or 0)
    max_score = int(porutham.get('max_score') or 10)
    matched_count = sum(1 for v in poruthams.values() if v)
    unmatched_count = max_score - matched_count

    porutham_table = [
        {
            'key': key,
            'label': label,
            'matched': bool(poruthams.get(key)),
        }
        for key, label in PORUTHAM_ROWS
    ]

    bride_name = (bride_hp.pr_name or bride_user.name or '').strip()
    groom_name = (groom_hp.pr_name or groom_user.name or '').strip()
    generated_at = timezone.localtime(timezone.now())

    return {
        'bride_name': bride_name,
        'groom_name': groom_name,
        'generated_date': generated_at.strftime('%d-%m-%Y %H:%M'),
        'score': score,
        'max_score': max_score,
        'overall_result': porutham.get('overall_result') or porutham.get('result') or '',
        'matched_count': matched_count,
        'unmatched_count': unmatched_count,
        'score_color': _score_color(score),
        'porutham_table': porutham_table,
        'bride': _person_dict(bride_hp, bride_user, bride_photo),
        'groom': _person_dict(groom_hp, groom_user, groom_photo),
    }


def generate_match_report_pdf(
    bride_hp,
    groom_hp,
    bride_user,
    groom_user,
    bride_photo=None,
    groom_photo=None,
) -> tuple[bytes, str]:
    ctx = build_match_report_context(
        bride_hp,
        groom_hp,
        bride_user,
        groom_user,
        bride_photo=bride_photo,
        groom_photo=groom_photo,
    )
    html = render_to_string('astrology/match_report.html', ctx)
    try:
        from weasyprint import HTML
        base = str(settings.MEDIA_ROOT) if settings.MEDIA_ROOT else None
        return HTML(string=html, base_url=base).write_pdf(), 'pdf'
    except Exception:
        return html.encode('utf-8'), 'html'
