"""One-page MVP Thalakuri PDF — condensed grahanila snapshot (ReportLab)."""
from io import BytesIO

from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from .utils import PLANET_FULL_NAMES


def build_thalakuri_pdf(horoscope, user, _profile) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_h = A4[1]
    y = page_h - 2 * cm

    c.setFont('Helvetica-Bold', 14)
    c.drawString(2 * cm, y, 'Thalakuri (Short horoscope)')
    y -= 0.9 * cm
    c.setFont('Helvetica', 9)
    c.drawString(2 * cm, y, f"{user.name or '-'} — {user.matri_id or '-'} — DOB {horoscope.date_of_birth}")
    y -= 0.45 * cm
    c.drawString(
        2 * cm,
        y,
        f"Lagna {horoscope.lagna} | Rasi {horoscope.rasi} | {horoscope.nakshatra} P{horoscope.nakshatra_pada}",
    )
    y -= 0.8 * cm
    c.setFont('Helvetica-Bold', 10)
    c.drawString(2 * cm, y, 'Planets (rasi)')
    y -= 0.5 * cm
    c.setFont('Helvetica', 9)
    grahanila = horoscope.grahanila or {}
    planets = grahanila.get('planets') or {}
    order = ('sun', 'moon', 'mars', 'mercury', 'jupiter', 'venus', 'saturn', 'rahu', 'ketu')
    for key in order:
        if key not in planets:
            continue
        info = planets[key] or {}
        rasi = info.get('rasi', '')
        name = PLANET_FULL_NAMES.get(key, key)
        line = f"{name}: {rasi}"
        c.drawString(2 * cm, y, line[:40])
        y -= 0.38 * cm
        if y < 3 * cm:
            break

    c.setFont('Helvetica-Oblique', 8)
    c.drawString(2 * cm, 2 * cm, f"Generated {timezone.now().isoformat()} — Thalakuri MVP.")
    c.save()
    buffer.seek(0)
    return buffer.read()
