"""Multi-page MVP Jathakam PDF from stored Horoscope (ReportLab, English labels)."""
from io import BytesIO

from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from .utils import PLANET_FULL_NAMES
from .vimshottari_service import vimshottari_mahadasha_state


def build_jathakam_pdf(horoscope, user, _profile) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_h = A4[1]
    y = page_h - 2 * cm

    def step(dy: float):
        nonlocal y
        y -= dy
        if y < 2.5 * cm:
            c.showPage()
            y = page_h - 2 * cm

    c.setFont('Helvetica-Bold', 16)
    c.drawString(2 * cm, y, 'Jathakam (Horoscope summary)')
    step(1.2 * cm)
    c.setFont('Helvetica', 10)
    for line in (
        f"Name: {user.name or '-'}",
        f"Matri ID: {user.matri_id or '-'}",
        f"Date of birth: {horoscope.date_of_birth}",
        f"Time of birth: {horoscope.time_of_birth}",
        f"Place of birth: {horoscope.place_of_birth}",
    ):
        c.drawString(2 * cm, y, line[:100])
        step(0.5 * cm)
    step(0.4 * cm)

    c.setFont('Helvetica-Bold', 12)
    c.drawString(2 * cm, y, 'Lagna / Rasi / Nakshatra')
    step(0.65 * cm)
    c.setFont('Helvetica', 10)
    for line in (
        f"Lagna: {horoscope.lagna}",
        f"Rasi (Moon): {horoscope.rasi}",
        f"Nakshatra: {horoscope.nakshatra} (Pada {horoscope.nakshatra_pada})",
        f"Gana: {horoscope.gana}, Yoni: {horoscope.yoni}, Nadi: {horoscope.nadi}, Rajju: {horoscope.rajju}",
    ):
        c.drawString(2 * cm, y, line[:120])
        step(0.42 * cm)

    step(0.4 * cm)
    c.setFont('Helvetica-Bold', 12)
    c.drawString(2 * cm, y, 'Grahanila')
    step(0.65 * cm)
    c.setFont('Helvetica', 10)
    grahanila = horoscope.grahanila or {}
    lag = grahanila.get('lagna_longitude')
    if lag is not None:
        c.drawString(2 * cm, y, f"Lagna longitude: {float(lag):.4f}")
        step(0.42 * cm)
    planets = grahanila.get('planets') or {}
    order = ('sun', 'moon', 'mars', 'mercury', 'jupiter', 'venus', 'saturn', 'rahu', 'ketu')
    for key in order:
        if key not in planets:
            continue
        info = planets[key] or {}
        lon = info.get('longitude')
        rasi = info.get('rasi', '')
        name = PLANET_FULL_NAMES.get(key, key)
        if lon is not None:
            line = f"{name}: {float(lon):.4f} deg — {rasi}"
        else:
            line = f"{name}: {rasi}"
        c.drawString(2 * cm, y, line[:110])
        step(0.4 * cm)

    st = vimshottari_mahadasha_state(horoscope, ref_utc=timezone.now())
    if st:
        step(0.35 * cm)
        c.setFont('Helvetica-Bold', 12)
        c.drawString(2 * cm, y, 'Vimshottari (Mahadasha)')
        step(0.65 * cm)
        c.setFont('Helvetica', 10)
        line = f"Lord: {st.get('lord', '')} — remaining ~ {st.get('remaining_label', '')}"
        c.drawString(2 * cm, y, line[:120])
        step(0.45 * cm)

    c.setFont('Helvetica-Oblique', 8)
    c.drawString(
        2 * cm,
        1.4 * cm,
        f"Generated {timezone.now().isoformat()} — MVP summary for personal use.",
    )
    c.save()
    buffer.seek(0)
    return buffer.read()
