import calendar
import os
from datetime import date, datetime, time
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.db import transaction as db_transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
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
    Spacer,
    Table,
    TableStyle,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.commissions.models import Commission
from admin_panel.permissions import IsBranchManager
from admin_panel.staff_mgmt.models import StaffProfile
from master.models import Branch as MasterBranch

from .models import SalaryRecord
from .serializers import (
    BranchSalaryRecordDetailSerializer,
    BranchSalaryRecordListSerializer,
    SalaryRecordListSerializer,
    SalaryRecordSerializer,
    _role_can_approve,
    _role_can_generate,
    _role_can_mark_paid,
)


def _escape_pdf_text(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(lines: list[str]) -> bytes:
    text_lines = ["BT", "/F1 12 Tf", "50 780 Td"]
    for i, line in enumerate(lines):
        if i:
            text_lines.append("0 -18 Td")
        text_lines.append(f"({_escape_pdf_text(line)}) Tj")
    text_lines.append("ET")
    stream = "\n".join(text_lines).encode("latin-1", errors="replace")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        b"4 0 obj\n<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    pdf = BytesIO()
    pdf.write(b"%PDF-1.4\n")
    offs = [0]
    for obj in objects:
        offs.append(pdf.tell())
        pdf.write(obj)
    xref = pdf.tell()
    pdf.write(f"xref\n0 {len(offs)}\n".encode())
    pdf.write(b"0000000000 65535 f \n")
    for o in offs[1:]:
        pdf.write(f"{o:010d} 00000 n \n".encode())
    pdf.write(f"trailer\n<< /Size {len(offs)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return pdf.getvalue()


_ONES = (
    "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
)
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")


def _two_digits_to_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    t, o = divmod(n, 10)
    return _TENS[t] + (f" {_ONES[o]}" if o else "")


def _three_digits_to_words(n: int) -> str:
    h, rest = divmod(n, 100)
    parts = []
    if h:
        parts.append(f"{_ONES[h]} Hundred")
    if rest:
        parts.append(_two_digits_to_words(rest))
    return " ".join(parts)


def _int_to_indian_words(n: int) -> str:
    """Convert a non-negative integer to words using the Indian numbering system."""
    if n == 0:
        return "Zero"
    parts: list[str] = []
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, n = divmod(n, 1_000)
    hundred = n
    if crore:
        parts.append(f"{_int_to_indian_words(crore)} Crore")
    if lakh:
        parts.append(f"{_two_digits_to_words(lakh)} Lakh")
    if thousand:
        parts.append(f"{_two_digits_to_words(thousand)} Thousand")
    if hundred:
        parts.append(_three_digits_to_words(hundred))
    return " ".join(p for p in parts if p)


def amount_to_words_inr(amount) -> str:
    """Format a Decimal/number as 'X Rupees and Y Paise Only' (Indian numbering)."""
    try:
        dec = Decimal(amount or 0)
    except Exception:
        dec = Decimal("0")
    if dec < 0:
        return "Minus " + amount_to_words_inr(-dec)
    rupees = int(dec)
    paise = int((dec - rupees) * 100)
    rupees_words = _int_to_indian_words(rupees)
    if paise:
        return f"{rupees_words} Rupees and {_two_digits_to_words(paise)} Paise Only"
    return f"{rupees_words} Rupees Only"


def _format_inr(amount) -> str:
    """Format a numeric amount using Indian digit grouping, e.g. 'Rs.12,345.67'."""
    try:
        dec = Decimal(amount or 0)
    except Exception:
        dec = Decimal("0")
    sign = "-" if dec < 0 else ""
    dec = abs(dec)
    whole = int(dec)
    paise = int((dec - whole) * 100)
    s = str(whole)
    if len(s) <= 3:
        grouped = s
    else:
        last3, rest = s[-3:], s[:-3]
        chunks: list[str] = []
        while len(rest) > 2:
            chunks.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            chunks.append(rest)
        grouped = ",".join(reversed(chunks)) + "," + last3
    return f"{sign}Rs.{grouped}.{paise:02d}"


def _salary_status_label(salary_obj: SalaryRecord) -> str:
    staff = getattr(salary_obj, "staff", None)
    if staff and getattr(staff, "is_active", False):
        return "Active"
    if staff:
        return "Inactive"
    return (salary_obj.status or "").title()


def _pay_date_for(salary_obj: SalaryRecord) -> date:
    """Return the date that should appear as 'Pay Date' on the slip."""
    paid_at = getattr(salary_obj, "paid_at", None)
    if paid_at:
        return timezone.localtime(paid_at).date()
    if salary_obj.month:
        last_day = calendar.monthrange(salary_obj.month.year, salary_obj.month.month)[1]
        return date(salary_obj.month.year, salary_obj.month.month, last_day)
    return timezone.localdate()


def _build_salary_slip_context(salary_obj: SalaryRecord) -> dict:
    now_local = timezone.localtime(timezone.now())
    branch = getattr(salary_obj, "branch", None)
    staff = getattr(salary_obj, "staff", None)

    basic = Decimal(getattr(salary_obj, "basic", 0) or 0)
    commission = Decimal(getattr(salary_obj, "commission", 0) or 0)
    allowances = Decimal(getattr(salary_obj, "allowances", 0) or 0)
    deductions = Decimal(getattr(salary_obj, "deductions", 0) or 0)
    gross = Decimal(getattr(salary_obj, "gross", 0) or 0) or (basic + commission + allowances)
    net = Decimal(getattr(salary_obj, "net", 0) or 0) or (gross - deductions)

    month = salary_obj.month
    if month:
        month_name = month.strftime("%B")
        year = month.strftime("%Y")
        days_in_month = calendar.monthrange(month.year, month.month)[1]
        pay_period = month.strftime("%b %Y")
    else:
        month_name = "-"
        year = "-"
        days_in_month = 0
        pay_period = "-"

    pay_date = _pay_date_for(salary_obj)

    earnings = [
        {"label": "Basic Salary", "amount": _format_inr(basic)},
        {"label": "Commission", "amount": _format_inr(commission)},
        {"label": "Allowances", "amount": _format_inr(allowances)},
    ]
    deduction_rows = [
        {"label": "Deductions", "amount": _format_inr(deductions)},
    ]

    company_address = (
        getattr(settings, "SALARY_SLIP_COMPANY_ADDRESS", "")
        or getattr(branch, "address", "")
        or ""
    ).strip()

    return {
        "company_name": getattr(settings, "SALARY_SLIP_COMPANY_NAME", "") or "Company Name",
        "company_address": company_address,
        "logo_url": getattr(settings, "SALARY_SLIP_LOGO_URL", "") or "",
        "month_name": month_name,
        "year": year,
        "employee_name": getattr(staff, "name", "") or "-",
        "employee_id": getattr(staff, "emp_code", "") or "-",
        "designation": getattr(staff, "designation", "") or "-",
        "branch_name": getattr(branch, "name", "") or "-",
        "status_label": _salary_status_label(salary_obj),
        "pay_period": pay_period,
        "pay_date": pay_date.strftime("%d %b %Y"),
        "paid_days": days_in_month,
        "lop_days": 0,
        "earnings": earnings,
        "deductions": deduction_rows,
        "gross_amount": _format_inr(gross),
        "total_deductions": _format_inr(deductions),
        "net_amount": _format_inr(net),
        "net_amount_words": amount_to_words_inr(net),
        "generated_on": now_local.strftime("%d %b %Y %I:%M %p"),
    }


# Matrimony brand palette (burgundy/magenta primary with soft pink tints).
_SLIP_PRIMARY = colors.HexColor("#8B2357")
_SLIP_PRIMARY_DARK = colors.HexColor("#5D1438")
_SLIP_TINT_BG = colors.HexColor("#F8E7EE")
_SLIP_TINT_BORDER = colors.HexColor("#ECC9D8")
_SLIP_GRAY_BAND = colors.HexColor("#F6EBF0")
_SLIP_GRAY_LINE = colors.HexColor("#EBD9E1")
_SLIP_HEAD_BG = colors.HexColor("#FBF2F6")
_SLIP_TEXT_DARK = colors.HexColor("#111827")
_SLIP_TEXT_MUTED = colors.HexColor("#6B4A57")


def _build_salary_slip_reportlab(context: dict) -> bytes:
    """Professional payslip rendered with ReportLab (no system deps)."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Payslip {context['employee_id']} {context['month_name']} {context['year']}",
    )
    full_w = doc.width

    ss = getSampleStyleSheet()

    def style(name, **kw):
        return ParagraphStyle(name, parent=ss["Normal"], **kw)

    company_name_style = style("cname", fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=colors.HexColor("#0F172A"))
    company_addr_style = style("caddr", fontSize=9, leading=12, textColor=_SLIP_TEXT_MUTED)
    payslip_title_style = style("ptitle", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=_SLIP_TEXT_DARK, spaceBefore=5)
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
    company_cell.append(
        Paragraph(
            f"Payslip for the Month of {context['month_name']} {context['year']}",
            payslip_title_style,
        )
    )

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

    # ----- Employee bar -----
    emp_left_w = full_w * 0.56
    emp_right_w = full_w - emp_left_w
    left_label_w = 30 * mm

    left_inner = Table(
        [
            [Paragraph("Employee Name", label_style), Paragraph(f": {context['employee_name']}", value_style)],
            [Paragraph("Employee ID", label_style), Paragraph(f": {context['employee_id']}", value_style)],
            [Paragraph("Pay Period", label_style), Paragraph(f": {context['pay_period']}", value_style)],
            [Paragraph("Pay Date", label_style), Paragraph(f": {context['pay_date']}", value_style)],
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

    right_days_w = emp_right_w - 28
    right_days = Table(
        [
            [Paragraph("Paid Days", label_style), Paragraph(f": {context['paid_days']}", value_style)],
            [Paragraph("LOP Days", label_style), Paragraph(f": {context['lop_days']}", value_style)],
        ],
        colWidths=[right_days_w * 0.55, right_days_w * 0.45],
    )
    right_days.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    right_cell = [
        Paragraph(context["net_amount"], netpay_amt_style),
        Paragraph("Total Net Pay", netpay_lbl_style),
        Spacer(1, 10),
        right_days,
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
    section_bar = Table([[Paragraph("Income Details", section_style)]], colWidths=[full_w])
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

    # ----- Earnings / Deductions columns -----
    def detail_table(header, rows, total_label, total_amount, col_w):
        data = [[Paragraph(header, th_style), Paragraph("Amount", th_amt_style)]]
        for r in rows:
            data.append([Paragraph(r["label"], cell_style), Paragraph(r["amount"], cell_amt_style)])
        data.append([Paragraph(total_label, total_style), Paragraph(total_amount, total_amt_style)])
        amt_w = 26 * mm
        t = Table(data, colWidths=[col_w - amt_w, amt_w])
        last = len(data) - 1
        t.setStyle(
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
                ]
            )
        )
        return t

    half_w = full_w / 2.0
    earnings_tbl = detail_table(
        "Earnings", context["earnings"], "Gross Earnings", context["gross_amount"], half_w
    )
    deductions_tbl = detail_table(
        "Deductions", context["deductions"], "Total Deductions", context["total_deductions"], half_w
    )
    income_tbl = Table([[earnings_tbl, deductions_tbl]], colWidths=[half_w, half_w])
    income_tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LINEAFTER", (0, 0), (0, 0), 1, _SLIP_GRAY_LINE),
                ("LINEBELOW", (0, 0), (-1, -1), 1, _SLIP_GRAY_LINE),
            ]
        )
    )

    # ----- Net payable -----
    net_block = Table(
        [
            [Paragraph("Total Net Payable", np_title_style)],
            [Paragraph("Gross Earnings - Total Deductions", np_formula_style)],
            [Paragraph(context["net_amount"], np_amount_style)],
            [Paragraph(f"Amount in Words: {context['net_amount_words']}", np_words_style)],
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

    inner = [header_tbl, emp_bar, section_bar, income_tbl, net_block, footer]
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


def build_salary_slip_pdf(salary_obj: SalaryRecord, request=None) -> bytes:
    context = _build_salary_slip_context(salary_obj)

    # Preferred: HTML via WeasyPrint when the runtime has the system deps (e.g. Linux/Docker).
    try:
        from weasyprint import HTML

        html_string = render_to_string("salary_slip.html", context)
        base_url = request.build_absolute_uri("/") if request else None
        return HTML(string=html_string, base_url=base_url).write_pdf()
    except Exception:
        pass

    # Professional cross-platform fallback (no system deps required).
    try:
        return _build_salary_slip_reportlab(context)
    except Exception:
        # Graceful fallback to preserve download availability if WeasyPrint/runtime deps are missing.
        lines: list[str] = [context["company_name"]]
        if context["company_address"]:
            lines.append(context["company_address"])
        lines.extend(
            [
                f"Payslip for the Month of {context['month_name']} {context['year']}",
                "",
                f"Employee Name : {context['employee_name']}",
                f"Employee ID   : {context['employee_id']}",
                f"Designation   : {context['designation']}",
                f"Branch        : {context['branch_name']}",
                f"Pay Period    : {context['pay_period']}",
                f"Pay Date      : {context['pay_date']}",
                f"Paid Days     : {context['paid_days']}",
                f"LOP Days      : {context['lop_days']}",
                "",
                "Earnings:",
            ]
        )
        for row in context["earnings"]:
            lines.append(f"  {row['label']:<22}{row['amount']:>16}")
        lines.append(f"  {'Gross Earnings':<22}{context['gross_amount']:>16}")
        lines.append("")
        lines.append("Deductions:")
        for row in context["deductions"]:
            lines.append(f"  {row['label']:<22}{row['amount']:>16}")
        lines.append(f"  {'Total Deductions':<22}{context['total_deductions']:>16}")
        lines.append("")
        lines.append(f"Total Net Payable : {context['net_amount']}")
        lines.append(f"Amount in Words   : {context['net_amount_words']}")
        lines.append("")
        lines.append("-- This is a system-generated document --")
        return _build_simple_pdf(lines)


def _staff_profile_for_admin_user(user):
    # Prefer direct relation (stable), keep mobile fallback for legacy rows.
    staff = StaffProfile.objects.filter(admin_user=user, is_deleted=False).first()
    if staff:
        return staff
    mobile = (getattr(user, "mobile", "") or "").strip()
    mobile10 = mobile[-10:] if mobile.startswith("+91") else mobile
    return StaffProfile.objects.filter(mobile=mobile10, is_deleted=False).first()


def _manager_branch_code(user):
    return (
        MasterBranch.objects.filter(pk=getattr(user, "branch_id", None))
        .values_list("code", flat=True)
        .first()
    )


def parse_month_string(s: str):
    s = (s or "").strip()
    if len(s) != 7 or s[4] != "-":
        return None, "Invalid month format, use YYYY-MM"
    try:
        y = int(s[:4])
        m = int(s[5:7])
        if m < 1 or m > 12:
            return None, "Invalid month format, use YYYY-MM"
        return date(y, m, 1), None
    except ValueError:
        return None, "Invalid month format, use YYYY-MM"


def parse_month_string_mm_yyyy(s: str):
    """Branch payroll month param: MM-YYYY (e.g. 02-2026)."""
    s = (s or "").strip()
    if len(s) != 7 or s[2] != "-":
        return None, "Invalid month format. Use MM-YYYY."
    try:
        m = int(s[:2])
        y = int(s[3:7])
        if m < 1 or m > 12:
            return None, "Invalid month format. Use MM-YYYY."
        return date(y, m, 1), None
    except ValueError:
        return None, "Invalid month format. Use MM-YYYY."


def month_paid_at_bounds(month_start: date):
    start = timezone.make_aware(datetime.combine(month_start, time.min))
    if month_start.month == 12:
        next_first = date(month_start.year + 1, 1, 1)
    else:
        next_first = date(month_start.year, month_start.month + 1, 1)
    end_exclusive = timezone.make_aware(datetime.combine(next_first, time.min))
    return start, end_exclusive


def month_date_bounds(month_start: date):
    if month_start.month == 12:
        next_first = date(month_start.year + 1, 1, 1)
    else:
        next_first = date(month_start.year, month_start.month + 1, 1)
    month_end = next_first - timezone.timedelta(days=1)
    return month_start, month_end


def is_future_month(month_start: date) -> bool:
    today = timezone.localdate()
    cur_first = date(today.year, today.month, 1)
    return month_start > cur_first


def commission_sum_paid_in_month(staff_id: int, month_start: date) -> Decimal:
    start, end_ex = month_paid_at_bounds(month_start)
    total = Commission.objects.filter(
        staff_id=staff_id,
        status=Commission.STATUS_PAID,
        paid_at__gte=start,
        paid_at__lt=end_ex,
    ).aggregate(t=Sum("commission_amt"))["t"]
    return Decimal(total or 0)


def _default_month_string() -> str:
    t = timezone.localdate()
    return f"{t.year:04d}-{t.month:02d}"


def _default_month_string_mm_yyyy() -> str:
    t = timezone.localdate()
    return f"{t.month:02d}-{t.year:04d}"


def _scoped_salary_queryset(request, force_staff_id=None):
    qs = SalaryRecord.objects.select_related("staff", "branch", "approved_by")
    role = getattr(request.user, "role", None)
    if force_staff_id is not None:
        return qs.filter(staff_id=force_staff_id)
    if role == AdminUser.ROLE_STAFF:
        staff = _staff_profile_for_admin_user(request.user)
        return qs.filter(staff=staff) if staff else qs.none()
    if role == AdminUser.ROLE_BRANCH_MANAGER:
        code = _manager_branch_code(request.user)
        return qs.filter(branch__code=code) if code else qs.none()
    return qs


def _apply_list_filters(request, qs, *, latest_month_when_missing: bool = False):
    month_s = (request.query_params.get("month") or "").strip()
    if month_s:
        md, err = parse_month_string(month_s)
        if err:
            return None, Response({"success": False, "error": {"code": 400, "message": err}}, status=400)
    else:
        if latest_month_when_missing:
            # For self payroll view, prefer a finalized month by default so UI doesn't
            # show a newer draft month while an older paid/approved month exists.
            latest_month = (
                qs.exclude(status=SalaryRecord.STATUS_DRAFT).order_by("-month").values_list("month", flat=True).first()
            )
            if not latest_month:
                latest_month = qs.order_by("-month").values_list("month", flat=True).first()
            md = latest_month or timezone.localdate().replace(day=1)
        else:
            md = parse_month_string(_default_month_string())[0]
    qs = qs.filter(month=md)

    status_filter = (request.query_params.get("status") or "").strip().lower()
    if status_filter:
        if status_filter not in {SalaryRecord.STATUS_DRAFT, SalaryRecord.STATUS_APPROVED, SalaryRecord.STATUS_PAID}:
            return None, Response(
                {"success": False, "error": {"code": 400, "message": "Invalid status filter"}},
                status=400,
            )
        qs = qs.filter(status=status_filter)

    branch_id = request.query_params.get("branch_id")
    if branch_id:
        role = getattr(request.user, "role", None)
        if role == AdminUser.ROLE_BRANCH_MANAGER:
            own_code = _manager_branch_code(request.user)
            from admin_panel.branches.models import Branch

            req_code = Branch.objects.filter(pk=branch_id).values_list("code", flat=True).first()
            if req_code != own_code:
                return None, Response(
                    {"success": False, "error": {"code": 403, "message": "Access denied"}},
                    status=403,
                )
        qs = qs.filter(branch_id=branch_id)

    return qs, None


class PayrollListAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            from rest_framework.settings import api_settings

            pagination_class = api_settings.DEFAULT_PAGINATION_CLASS
            self._paginator = pagination_class() if pagination_class else None
        return self._paginator

    def paginate_queryset(self, queryset, request):
        if self.paginator is None:
            return None
        return self.paginator.paginate_queryset(queryset, request, view=self)

    def get_paginated_response(self, data):
        return self.paginator.get_paginated_response(data)

    def get(self, request):
        qs = _scoped_salary_queryset(request)
        qs, err = _apply_list_filters(request, qs)
        if err:
            return err
        qs = qs.order_by("staff__name")
        page = self.paginate_queryset(qs, request)
        ser = SalaryRecordListSerializer(page if page is not None else qs, many=True)
        if page is not None:
            paged = self.get_paginated_response(ser.data)
            return Response({"success": True, "data": paged.data})
        return Response({"success": True, "data": {"count": len(ser.data), "results": ser.data}})


class PayrollSummaryAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = _scoped_salary_queryset(request)
        month_s = (request.query_params.get("month") or "").strip() or _default_month_string()
        md, err = parse_month_string(month_s)
        if err:
            return Response({"success": False, "error": {"code": 400, "message": err}}, status=400)
        qs = qs.filter(month=md)

        branch_id = request.query_params.get("branch_id")
        if branch_id:
            role = getattr(request.user, "role", None)
            if role == AdminUser.ROLE_BRANCH_MANAGER:
                own_code = _manager_branch_code(request.user)
                from admin_panel.branches.models import Branch

                req_code = Branch.objects.filter(pk=branch_id).values_list("code", flat=True).first()
                if req_code != own_code:
                    return Response(
                        {"success": False, "error": {"code": 403, "message": "Access denied"}},
                        status=403,
                    )
            qs = qs.filter(branch_id=branch_id)

        agg = qs.aggregate(
            total_net=Sum("net"),
            total_gross=Sum("gross"),
            staff_count=Count("id", distinct=True),
            pending_drafts=Count("id", filter=Q(status=SalaryRecord.STATUS_DRAFT)),
        )
        data = {
            "total_net_payroll": float(agg["total_net"] or 0),
            "total_gross": float(agg["total_gross"] or 0),
            "staff_count": agg["staff_count"] or 0,
            "pending_drafts": agg["pending_drafts"] or 0,
            "month": month_s,
        }
        return Response({"success": True, "data": data})


class GeneratePayrollAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _role_can_generate(request.user):
            return Response(
                {"success": False, "error": {"code": 403, "message": "Insufficient permissions"}},
                status=403,
            )
        month_s = (request.data.get("month") or "").strip()
        md, err = parse_month_string(month_s)
        if err:
            return Response({"success": False, "error": {"code": 400, "message": err}}, status=400)
        if is_future_month(md):
            return Response(
                {"success": False, "error": {"code": 400, "message": "Cannot generate salary for future months"}},
                status=400,
            )
        _, month_end = month_date_bounds(md)
        staff_qs = (
            StaffProfile.objects.filter(is_active=True, is_deleted=False)
            .filter(Q(joining_date__isnull=True) | Q(joining_date__lte=month_end))
            .select_related("branch")
        )
        created = 0
        skipped = 0
        with db_transaction.atomic():
            existing_staff_ids = set(
                SalaryRecord.objects.filter(month=md).values_list("staff_id", flat=True)
            )
            for sp in staff_qs:
                if sp.id in existing_staff_ids:
                    skipped += 1
                    continue
                comm = commission_sum_paid_in_month(sp.id, md)
                basic = Decimal(sp.basic_salary or 0)
                allowances = Decimal("0")
                deductions = Decimal("0")
                gross = basic + comm + allowances
                net = gross - deductions
                SalaryRecord.objects.create(
                    staff=sp,
                    branch=sp.branch,
                    month=md,
                    basic=basic,
                    commission=comm,
                    allowances=allowances,
                    deductions=deductions,
                    gross=gross,
                    net=net,
                    status=SalaryRecord.STATUS_DRAFT,
                )
                created += 1

        return Response(
            {
                "success": True,
                "data": {
                    "month": month_s,
                    "records_created": created,
                    "skipped_existing": skipped,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class PayrollDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        qs = _scoped_salary_queryset(request)
        obj = qs.filter(pk=pk).first()
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Salary record not found"}},
                status=404,
            )
        return Response({"success": True, "data": SalaryRecordSerializer(obj).data})


class ApprovePayrollAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not _role_can_approve(request.user):
            return Response(
                {"success": False, "error": {"code": 403, "message": "Insufficient permissions"}},
                status=403,
            )
        qs = SalaryRecord.objects.select_related("staff", "branch").filter(pk=pk)
        obj = qs.first()
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Salary record not found"}},
                status=404,
            )
        role = getattr(request.user, "role", None)
        if role == AdminUser.ROLE_BRANCH_MANAGER:
            code = _manager_branch_code(request.user)
            if not code or obj.branch.code != code:
                return Response(
                    {"success": False, "error": {"code": 403, "message": "Access denied"}},
                    status=403,
                )
        if obj.status != SalaryRecord.STATUS_DRAFT:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Only draft records can be approved"}},
                status=400,
            )
        obj.status = SalaryRecord.STATUS_APPROVED
        obj.approved_by = request.user
        obj.save(update_fields=["status", "approved_by", "updated_at"])
        return Response({"success": True, "data": SalaryRecordSerializer(obj).data})


class MarkPaidPayrollAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not _role_can_mark_paid(request.user):
            return Response(
                {"success": False, "error": {"code": 403, "message": "Insufficient permissions"}},
                status=403,
            )
        obj = SalaryRecord.objects.filter(pk=pk).first()
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Salary record not found"}},
                status=404,
            )
        if obj.status != SalaryRecord.STATUS_APPROVED:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Salary must be approved before marking as paid"},
                },
                status=400,
            )
        obj.status = SalaryRecord.STATUS_PAID
        obj.paid_at = timezone.now()
        obj.save(update_fields=["status", "paid_at", "updated_at"])
        return Response({"success": True, "data": SalaryRecordSerializer(obj).data})


class PayrollDownloadAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        qs = _scoped_salary_queryset(request)
        obj = qs.select_related("staff", "branch").filter(pk=pk).first()
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Salary record not found"}},
                status=404,
            )
        pdf = build_salary_slip_pdf(obj, request=request)
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="salary_{obj.id}_slip.pdf"'
        return resp


class StaffPayrollListAPIView(PayrollListAPIView):
    def get(self, request):
        role = getattr(request.user, "role", None)
        if role not in (AdminUser.ROLE_STAFF, AdminUser.ROLE_BRANCH_MANAGER):
            return Response(
                {"success": False, "error": {"code": 403, "message": "Insufficient permissions"}},
                status=403,
            )
        staff = _staff_profile_for_admin_user(request.user)
        if not staff:
            return Response(
                {"success": False, "error": {"code": 403, "message": "Profile not found for this user"}},
                status=403,
            )
        qs = _scoped_salary_queryset(request, force_staff_id=staff.id)
        qs, err = _apply_list_filters(request, qs, latest_month_when_missing=True)
        if err:
            return err
        qs = qs.order_by("-month")
        page = self.paginate_queryset(qs, request)
        ser = SalaryRecordListSerializer(page if page is not None else qs, many=True)
        if page is not None:
            paged = self.get_paginated_response(ser.data)
            return Response({"success": True, "data": paged.data})
        return Response({"success": True, "data": {"count": len(ser.data), "results": ser.data}})


def _branch_manager_code_or_error(request):
    code = _manager_branch_code(request.user)
    if not code:
        return None, Response(
            {
                "success": False,
                "error": {
                    "code": 400,
                    "message": "No branch assigned to your account. Contact admin.",
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return code, None


def _branch_payroll_qs_for_management(request):
    """Branch payroll for management views — excludes the manager's own staff profile."""
    code = _manager_branch_code(request.user)
    if not code:
        return SalaryRecord.objects.none()
    qs = SalaryRecord.objects.select_related("staff", "branch", "approved_by").filter(branch__code=code)
    manager_staff = _staff_profile_for_admin_user(request.user)
    if manager_staff:
        qs = qs.exclude(staff_id=manager_staff.id)
    return qs


def _salary_record_for_branch_manager(request, pk, *, wrong_branch_as_404: bool):
    code, err = _branch_manager_code_or_error(request)
    if err:
        return None, err
    obj = (
        SalaryRecord.objects.select_related("staff", "branch", "approved_by")
        .filter(pk=pk)
        .first()
    )
    if not obj:
        return None, Response(
            {"success": False, "error": {"code": 404, "message": "Salary record not found"}},
            status=status.HTTP_404_NOT_FOUND,
        )
    if obj.branch.code != code:
        if wrong_branch_as_404:
            return None, Response(
                {"success": False, "error": {"code": 404, "message": "Salary record not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return None, Response(
            {
                "success": False,
                "error": {
                    "code": 403,
                    "message": "You can only approve salary records for your own branch staff.",
                },
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    manager_staff = _staff_profile_for_admin_user(request.user)
    if manager_staff and obj.staff_id == manager_staff.id:
        if wrong_branch_as_404:
            return None, Response(
                {"success": False, "error": {"code": 404, "message": "Salary record not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return None, Response(
            {
                "success": False,
                "error": {
                    "code": 403,
                    "message": "You cannot manage your own salary records here. Use My Salary.",
                },
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return obj, None


def _apply_branch_list_filters(request, qs):
    month_s = (request.query_params.get("month") or "").strip()
    if month_s:
        md, err = parse_month_string_mm_yyyy(month_s)
        if err:
            return None, None, Response({"success": False, "error": {"code": 400, "message": err}}, status=400)
    else:
        # When month is omitted, use the latest available salary month for this branch.
        # This prevents empty table responses for branches that don't have current-month payroll yet.
        latest_month = qs.order_by("-month").values_list("month", flat=True).first()
        md = latest_month or timezone.localdate().replace(day=1)
    qs = qs.filter(month=md)
    resolved_month = f"{md.month:02d}-{md.year:04d}"

    status_filter = (request.query_params.get("status") or "").strip().lower()
    if status_filter:
        if status_filter not in {SalaryRecord.STATUS_DRAFT, SalaryRecord.STATUS_APPROVED, SalaryRecord.STATUS_PAID}:
            return None, None, Response(
                {"success": False, "error": {"code": 400, "message": "Invalid status filter"}},
                status=400,
            )
        qs = qs.filter(status=status_filter)

    return qs, resolved_month, None


class BranchPayrollSummaryAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def get(self, request):
        code, err = _branch_manager_code_or_error(request)
        if err:
            return err
        qs_all = _branch_payroll_qs_for_management(request)
        month_s = (request.query_params.get("month") or "").strip()
        if month_s:
            md, merr = parse_month_string_mm_yyyy(month_s)
            if merr:
                return Response({"success": False, "error": {"code": 400, "message": merr}}, status=400)
        else:
            latest_month = qs_all.order_by("-month").values_list("month", flat=True).first()
            md = latest_month or timezone.localdate().replace(day=1)
            month_s = f"{md.month:02d}-{md.year:04d}"

        qs = qs_all.filter(month=md)
        agg = qs.aggregate(
            branch_net=Sum("net"),
            staff_count=Count("id", distinct=True),
            pending_drafts=Count("id", filter=Q(status=SalaryRecord.STATUS_DRAFT)),
            paid_count=Count("id", filter=Q(status=SalaryRecord.STATUS_PAID)),
        )
        return Response(
            {
                "success": True,
                "data": {
                    "month": month_s,
                    "branch_net_payroll": float(agg["branch_net"] or 0),
                    "branch_net_pay": float(agg["branch_net"] or 0),
                    "staff_count": agg["staff_count"] or 0,
                    "pending_drafts": agg["pending_drafts"] or 0,
                    "paid_count": agg["paid_count"] or 0,
                    "paid": agg["paid_count"] or 0,
                },
            }
        )


class BranchPayrollListAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            from rest_framework.settings import api_settings

            pagination_class = api_settings.DEFAULT_PAGINATION_CLASS
            self._paginator = pagination_class() if pagination_class else None
        return self._paginator

    def paginate_queryset(self, queryset, request):
        if self.paginator is None:
            return None
        return self.paginator.paginate_queryset(queryset, request, view=self)

    def get_paginated_response(self, data):
        return self.paginator.get_paginated_response(data)

    def get(self, request):
        code, err = _branch_manager_code_or_error(request)
        if err:
            return err
        qs = _branch_payroll_qs_for_management(request)
        qs, resolved_month, ferr = _apply_branch_list_filters(request, qs)
        if ferr:
            return ferr
        qs = qs.order_by("staff__name")
        page = self.paginate_queryset(qs, request)
        ser = BranchSalaryRecordListSerializer(
            page if page is not None else qs,
            many=True,
            context={"request": request},
        )
        if page is not None:
            paged = self.get_paginated_response(ser.data)
            paged.data["month"] = resolved_month
            return Response({"success": True, "data": paged.data})
        return Response(
            {
                "success": True,
                "data": {
                    "count": len(ser.data),
                    "results": ser.data,
                    "month": resolved_month,
                },
            }
        )


class BranchPayrollDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def get(self, request, pk):
        obj, err = _salary_record_for_branch_manager(request, pk, wrong_branch_as_404=True)
        if err:
            return err
        return Response(
            {
                "success": True,
                "data": BranchSalaryRecordDetailSerializer(obj, context={"request": request}).data,
            }
        )


class BranchApprovePayrollAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def patch(self, request, pk):
        obj, err = _salary_record_for_branch_manager(request, pk, wrong_branch_as_404=False)
        if err:
            return err
        if obj.status != SalaryRecord.STATUS_DRAFT:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Only draft records can be approved."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj.status = SalaryRecord.STATUS_APPROVED
        obj.approved_by = request.user
        obj.save(update_fields=["status", "approved_by", "updated_at"])
        obj = SalaryRecord.objects.select_related("staff", "branch", "approved_by").filter(pk=obj.pk).first()
        return Response(
            {
                "success": True,
                "data": BranchSalaryRecordDetailSerializer(obj, context={"request": request}).data,
            }
        )


class BranchGeneratePayrollForbiddenAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def post(self, request):
        return Response(
            {
                "success": False,
                "error": {"code": 403, "message": "Salary generation is an admin-only action."},
            },
            status=status.HTTP_403_FORBIDDEN,
        )


class BranchMarkPaidPayrollForbiddenAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def patch(self, request, pk):
        return Response(
            {
                "success": False,
                "error": {"code": 403, "message": "Marking salary as paid is an admin-only action."},
            },
            status=status.HTTP_403_FORBIDDEN,
        )


class BranchPayrollDownloadAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def get(self, request, pk):
        obj, err = _salary_record_for_branch_manager(request, pk, wrong_branch_as_404=True)
        if err:
            return err
        pdf = build_salary_slip_pdf(obj, request=request)
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="salary_{obj.id}_slip.pdf"'
        return resp
