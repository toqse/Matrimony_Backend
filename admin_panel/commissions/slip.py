"""
Commission slip PDF generation.

Reuses the salary slip theme/helpers so commission slips share the same look:
WeasyPrint (HTML template) when system deps exist, ReportLab as a cross-platform
fallback, and a plain-text PDF as a last resort.
"""
from __future__ import annotations

import os
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

# Shared formatting helpers, theme colors, and the plain-text PDF fallback.
from admin_panel.payroll.views import (
    _SLIP_GRAY_BAND,
    _SLIP_GRAY_LINE,
    _SLIP_HEAD_BG,
    _SLIP_PRIMARY,
    _SLIP_PRIMARY_DARK,
    _SLIP_TEXT_DARK,
    _SLIP_TEXT_MUTED,
    _SLIP_TINT_BG,
    _SLIP_TINT_BORDER,
    _build_simple_pdf,
    _format_inr,
    amount_to_words_inr,
)


def _plan_name_for(obj) -> str:
    if obj.subscription_id and getattr(obj.subscription, "plan", None):
        return obj.subscription.plan.name or ""
    if obj.plan_id and getattr(obj, "plan", None):
        return obj.plan.name or ""
    return ""


def _format_rate(rate) -> str:
    try:
        return f"{Decimal(rate or 0):.2f}%"
    except Exception:
        return f"{rate}%"


def _build_commission_slip_context(obj) -> dict:
    now_local = timezone.localtime(timezone.now())
    staff = getattr(obj, "staff", None)
    branch = getattr(obj, "branch", None)
    customer = getattr(obj, "customer", None)

    commission_amt = Decimal(getattr(obj, "commission_amt", 0) or 0)

    company_address = (
        getattr(settings, "SALARY_SLIP_COMPANY_ADDRESS", "")
        or getattr(branch, "address", "")
        or ""
    ).strip()

    customer_label = "-"
    if customer is not None:
        name = getattr(customer, "name", "") or ""
        matri_id = getattr(customer, "matri_id", "") or ""
        customer_label = f"{name} ({matri_id})".strip() if matri_id else (name or "-")

    return {
        "company_name": getattr(settings, "SALARY_SLIP_COMPANY_NAME", "") or "Company Name",
        "company_address": company_address,
        "logo_url": getattr(settings, "SALARY_SLIP_LOGO_URL", "") or "",
        "staff_name": getattr(staff, "name", "") or "-",
        "staff_id": getattr(staff, "emp_code", "") or "-",
        "branch_name": getattr(branch, "name", "") or "-",
        "date": obj.created_at.date().strftime("%d %b %Y") if getattr(obj, "created_at", None) else "-",
        "customer": customer_label,
        "plan_name": _plan_name_for(obj) or "-",
        "sale_amount": _format_inr(getattr(obj, "sale_amount", 0) or 0),
        "commission_rate": _format_rate(getattr(obj, "commission_rate", 0)),
        "status_label": (getattr(obj, "status", "") or "-").title(),
        "commission_amount": _format_inr(commission_amt),
        "commission_amount_words": amount_to_words_inr(commission_amt),
        "generated_on": now_local.strftime("%d %b %Y %I:%M %p"),
    }


def _build_commission_slip_reportlab(context: dict) -> bytes:
    """Commission slip rendered with ReportLab (no system deps), matching the salary slip theme."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Commission Slip {context['staff_id']}",
    )
    full_w = doc.width
    ss = getSampleStyleSheet()

    def style(name, **kw):
        return ParagraphStyle(name, parent=ss["Normal"], **kw)

    company_name_style = style("cname", fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=colors.HexColor("#0F172A"))
    company_addr_style = style("caddr", fontSize=9, leading=12, textColor=_SLIP_TEXT_MUTED)
    slip_title_style = style("stitle", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=_SLIP_TEXT_DARK, spaceBefore=5)
    logo_ph_style = style("logoph", fontSize=8, leading=10, textColor=colors.HexColor("#94A3B8"), alignment=1)
    label_style = style("lbl", fontSize=9.5, leading=14, textColor=_SLIP_TEXT_MUTED)
    value_style = style("val", fontName="Helvetica-Bold", fontSize=9.5, leading=14, textColor=_SLIP_TEXT_DARK)
    netpay_amt_style = style("netamt", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=_SLIP_PRIMARY, alignment=2)
    netpay_lbl_style = style("netlbl", fontSize=8.5, leading=11, textColor=_SLIP_TEXT_MUTED, alignment=2)
    section_style = style("sec", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=_SLIP_TEXT_DARK)
    th_style = style("th", fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=colors.HexColor("#374151"))
    th_amt_style = ParagraphStyle("thamt", parent=th_style, alignment=2)
    cell_style = style("cell", fontSize=9.5, leading=12, textColor=colors.HexColor("#1F2937"))
    cell_amt_style = ParagraphStyle("cellamt", parent=cell_style, alignment=2)
    total_style = style("tot", fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=_SLIP_TEXT_DARK)
    total_amt_style = ParagraphStyle("totamt", parent=total_style, alignment=2)
    np_title_style = style("nptitle", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=_SLIP_PRIMARY_DARK, alignment=1)
    np_formula_style = style("npf", fontSize=9, leading=12, textColor=_SLIP_TEXT_MUTED, alignment=1)
    np_amount_style = style("npa", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=_SLIP_PRIMARY, alignment=1)
    np_words_style = style("npw", fontSize=9, leading=12, textColor=_SLIP_TEXT_MUTED, alignment=1)
    footer_style = style("ft", fontSize=8.5, leading=11, textColor=colors.HexColor("#9CA3AF"), alignment=1)

    # ----- Header (logo + company) -----
    logo_path = context.get("logo_url") or ""
    logo_cell = None
    try:
        if logo_path and not logo_path.startswith(("http://", "https://")) and os.path.exists(logo_path):
            logo_cell = RLImage(logo_path, width=20 * mm, height=20 * mm)
    except Exception:
        logo_cell = None
    if logo_cell is None:
        logo_cell = Paragraph("Logo", logo_ph_style)

    company_cell = [Paragraph(context["company_name"], company_name_style)]
    if context.get("company_address"):
        company_cell.append(
            Paragraph(str(context["company_address"]).replace("\n", "<br/>"), company_addr_style)
        )
    company_cell.append(Paragraph("Commission Slip", slip_title_style))

    logo_w = 24 * mm
    header_tbl = Table([[logo_cell, company_cell]], colWidths=[logo_w, full_w - logo_w])
    header_tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("BOX", (0, 0), (0, 0), 0.8, _SLIP_TINT_BORDER, None, [2, 2]),
            ]
        )
    )

    # ----- Staff bar -----
    emp_left_w = full_w * 0.62
    emp_right_w = full_w - emp_left_w
    left_label_w = 30 * mm

    left_inner = Table(
        [
            [Paragraph("Staff Name", label_style), Paragraph(f": {context['staff_name']}", value_style)],
            [Paragraph("Staff ID", label_style), Paragraph(f": {context['staff_id']}", value_style)],
            [Paragraph("Branch", label_style), Paragraph(f": {context['branch_name']}", value_style)],
            [Paragraph("Date", label_style), Paragraph(f": {context['date']}", value_style)],
        ],
        colWidths=[left_label_w, emp_left_w - left_label_w - 28],
    )
    left_inner.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    right_cell = [
        Paragraph(context["commission_amount"], netpay_amt_style),
        Paragraph("Total Commission", netpay_lbl_style),
    ]

    emp_bar = Table([[left_inner, right_cell]], colWidths=[emp_left_w, emp_right_w])
    emp_bar.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _SLIP_TINT_BG),
                ("LINEABOVE", (0, 0), (-1, 0), 1, _SLIP_TINT_BORDER),
                ("LINEBELOW", (0, 0), (-1, -1), 1, _SLIP_TINT_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )

    # ----- Section title -----
    section_bar = Table([[Paragraph("Commission Details", section_style)]], colWidths=[full_w])
    section_bar.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _SLIP_GRAY_BAND),
                ("LINEABOVE", (0, 0), (-1, 0), 1, _SLIP_GRAY_LINE),
                ("LINEBELOW", (0, 0), (-1, -1), 1, _SLIP_GRAY_LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    # ----- Details table -----
    detail_rows = [
        ("Customer", context["customer"]),
        ("Plan", context["plan_name"]),
        ("Sale Amount", context["sale_amount"]),
        ("Commission Rate", context["commission_rate"]),
        ("Status", context["status_label"]),
    ]
    data = [[Paragraph("Description", th_style), Paragraph("Details", th_amt_style)]]
    for label, val in detail_rows:
        data.append([Paragraph(label, cell_style), Paragraph(str(val), cell_amt_style)])
    data.append(
        [Paragraph("Commission Earned", total_style), Paragraph(context["commission_amount"], total_amt_style)]
    )
    amt_w = 60 * mm
    detail_tbl = Table(data, colWidths=[full_w - amt_w, amt_w])
    last = len(data) - 1
    detail_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _SLIP_HEAD_BG),
                ("LINEBELOW", (0, 0), (-1, 0), 1, _SLIP_GRAY_LINE),
                ("BACKGROUND", (0, last), (-1, last), _SLIP_HEAD_BG),
                ("LINEABOVE", (0, last), (-1, last), 1, _SLIP_TINT_BORDER),
                ("LINEBELOW", (0, 1), (-1, last - 1), 0.5, colors.HexColor("#EEF2F7")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, last), (-1, last), 1, _SLIP_GRAY_LINE),
            ]
        )
    )

    # ----- Net payable -----
    net_block = Table(
        [
            [Paragraph("Total Commission Payable", np_title_style)],
            [Paragraph("Sale Amount x Commission Rate", np_formula_style)],
            [Paragraph(context["commission_amount"], np_amount_style)],
            [Paragraph(f"Amount in Words: {context['commission_amount_words']}", np_words_style)],
        ],
        colWidths=[full_w],
    )
    net_block.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _SLIP_TINT_BG),
                ("LINEBELOW", (0, 0), (-1, -1), 1, _SLIP_TINT_BORDER),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (0, 0), 14),
                ("BOTTOMPADDING", (0, 0), (0, 0), 2),
                ("TOPPADDING", (0, 1), (0, 1), 0),
                ("BOTTOMPADDING", (0, 1), (0, 1), 4),
                ("TOPPADDING", (0, 2), (0, 2), 0),
                ("BOTTOMPADDING", (0, 2), (0, 2), 4),
                ("TOPPADDING", (0, 3), (0, 3), 0),
                ("BOTTOMPADDING", (0, 3), (0, 3), 14),
            ]
        )
    )

    footer = Table([[Paragraph("-- This is a system-generated document. --", footer_style)]], colWidths=[full_w])
    footer.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    inner = [header_tbl, emp_bar, section_bar, detail_tbl, net_block, footer]
    card = Table([[inner]], colWidths=[full_w])
    card.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, _SLIP_GRAY_LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    doc.build([card])
    return buffer.getvalue()


def build_commission_slip_pdf(commission_obj, request=None) -> bytes:
    context = _build_commission_slip_context(commission_obj)

    # Preferred: HTML via WeasyPrint when the runtime has the system deps (e.g. Linux/Docker).
    try:
        from weasyprint import HTML

        html_string = render_to_string("commission_slip.html", context)
        base_url = request.build_absolute_uri("/") if request else None
        return HTML(string=html_string, base_url=base_url).write_pdf()
    except Exception:
        pass

    # Professional cross-platform fallback (no system deps required).
    try:
        return _build_commission_slip_reportlab(context)
    except Exception:
        lines = [context["company_name"]]
        if context["company_address"]:
            lines.append(context["company_address"])
        lines.extend(
            [
                "Commission Slip",
                "",
                f"Staff        : {context['staff_name']} ({context['staff_id']})",
                f"Branch       : {context['branch_name']}",
                f"Date         : {context['date']}",
                f"Customer     : {context['customer']}",
                f"Plan         : {context['plan_name']}",
                f"Sale Amount  : {context['sale_amount']}",
                f"Rate         : {context['commission_rate']}",
                f"Status       : {context['status_label']}",
                "",
                f"Total Commission : {context['commission_amount']}",
                f"Amount in Words  : {context['commission_amount_words']}",
                "",
                "-- This is a system-generated document --",
            ]
        )
        return _build_simple_pdf(lines)
