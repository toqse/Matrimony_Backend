"""Build Porutham match report as PDF (ReportLab)."""
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas


def build_match_report_pdf(
    bride_matri_id: str,
    groom_matri_id: str,
    bride_summary: dict,
    groom_summary: dict,
    porutham_result: dict,
) -> bytes:
    buffer = BytesIO()
    page_w, page_h = A4
    c = canvas.Canvas(buffer, pagesize=A4)
    y = page_h - 2 * cm

    c.setFont('Helvetica-Bold', 16)
    c.drawString(2 * cm, y, 'Horoscope Match Report (Porutham)')
    y -= 1.2 * cm

    c.setFont('Helvetica', 11)
    c.drawString(2 * cm, y, f'Bride: {bride_matri_id}')
    y -= 0.6 * cm
    c.drawString(2 * cm, y, f'Groom: {groom_matri_id}')
    y -= 1 * cm

    c.setFont('Helvetica-Bold', 12)
    c.drawString(2 * cm, y, 'Profiles')
    y -= 0.7 * cm
    c.setFont('Helvetica', 10)
    for label, summary in (('Bride', bride_summary), ('Groom', groom_summary)):
        line = (
            f'{label}: Rasi {summary.get("rasi", "")}, Nakshatra {summary.get("nakshatra", "")} '
            f'(Pada {summary.get("nakshatra_pada", "")}), Gana {summary.get("gana", "")}'
        )
        c.drawString(2 * cm, y, line[:120])
        y -= 0.5 * cm
    y -= 0.5 * cm

    c.setFont('Helvetica-Bold', 12)
    c.drawString(2 * cm, y, 'Poruthams')
    y -= 0.7 * cm
    c.setFont('Helvetica', 10)
    poruthams = porutham_result.get('poruthams') or {}
    koota_points = porutham_result.get('koota_points') or {}
    for name in (
        'dina', 'gana', 'mahendra', 'sthree_deergha', 'yoni',
        'rasi', 'rasi_adhipathi', 'vasya', 'rajju', 'vedha',
    ):
        ok = poruthams.get(name)
        mark = 'Yes' if ok else 'No'
        pts = koota_points.get(name)
        if pts is not None:
            line = f'{name.replace("_", " ").title()}: {mark} ({float(pts):g} pt)'
        else:
            line = f'{name.replace("_", " ").title()}: {mark}'
        c.drawString(2 * cm, y, line)
        y -= 0.45 * cm
        if y < 3 * cm:
            c.showPage()
            y = page_h - 2 * cm
            c.setFont('Helvetica', 10)

    y -= 0.5 * cm
    c.setFont('Helvetica-Bold', 11)
    score = porutham_result.get('score')
    max_score = porutham_result.get('max_score', 10)
    result = porutham_result.get('result', '')
    c.drawString(2 * cm, y, f'Score: {score} / {max_score} (fractional Dashakoot)')
    y -= 0.6 * cm
    c.drawString(2 * cm, y, f'Result: {result}')

    c.save()
    buffer.seek(0)
    return buffer.read()
