import os
from io import BytesIO

from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch
from master.models import Branch as MasterBranch

from .models import StaffProfile
from .serializers import StaffSerializer
from .soft_delete import release_staff_unique_fields


def _escape_pdf_text(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(lines: list[str]) -> bytes:
    y_start = 780
    line_gap = 18
    text_lines = ["BT", "/F1 12 Tf", f"50 {y_start} Td"]
    first = True
    for line in lines:
        if not first:
            text_lines.append(f"0 -{line_gap} Td")
        text_lines.append(f"({_escape_pdf_text(line)}) Tj")
        first = False
    text_lines.append("ET")
    stream = "\n".join(text_lines).encode("latin-1", errors="replace")

    objects = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    )
    objects.append(
        b"4 0 obj\n<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    pdf = BytesIO()
    pdf.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(pdf.tell())
        pdf.write(obj)
    xref_pos = pdf.tell()
    pdf.write(f"xref\n0 {len(offsets)}\n".encode())
    pdf.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.write(f"{off:010d} 00000 n \n".encode())
    pdf.write(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF"
        ).encode()
    )
    return pdf.getvalue()


_REPORT_PRIMARY = colors.HexColor("#7A1F3D")
_REPORT_LIGHT = colors.HexColor("#F1E4E9")
_REPORT_MUTED = colors.HexColor("#6B7280")
_REPORT_DARK = colors.HexColor("#1F2937")


def _report_text(value, dash="-") -> str:
    s = "" if value is None else str(value).strip()
    return s if s else dash


def _report_money(value) -> str:
    try:
        return f"Rs. {float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "Rs. 0.00"


def _build_staff_report_pdf(staff) -> bytes:
    """Resume-style staff profile report (ReportLab platypus)."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"{staff.emp_code} Staff Report",
    )

    styles = getSampleStyleSheet()
    eyebrow_style = ParagraphStyle(
        "eyebrow", parent=styles["Normal"], fontSize=8, leading=11,
        textColor=colors.white, fontName="Helvetica-Bold", spaceAfter=2,
    )
    name_style = ParagraphStyle(
        "name", parent=styles["Title"], fontSize=22, leading=26,
        textColor=colors.white, spaceAfter=2,
    )
    sub_style = ParagraphStyle(
        "sub", parent=styles["Normal"], fontSize=10.5, leading=15, textColor=colors.white,
    )
    section_style = ParagraphStyle(
        "section", parent=styles["Normal"], fontSize=12, leading=15,
        textColor=_REPORT_PRIMARY, fontName="Helvetica-Bold", spaceBefore=2, spaceAfter=2,
    )
    label_style = ParagraphStyle(
        "label", parent=styles["Normal"], fontSize=7.5, leading=10,
        textColor=_REPORT_MUTED, fontName="Helvetica-Bold",
    )
    value_style = ParagraphStyle(
        "value", parent=styles["Normal"], fontSize=10.5, leading=14, textColor=_REPORT_DARK,
    )
    footer_style = ParagraphStyle(
        "footer", parent=styles["Normal"], fontSize=8, leading=11, textColor=_REPORT_MUTED,
    )

    try:
        role = staff.admin_user.role
    except Exception:
        role = ""
    role_label = {"branch_manager": "Branch Manager", "staff": "Staff"}.get(role, role or "-")

    mobile = (staff.mobile or "").strip()
    mobile_disp = f"+91 {mobile}" if mobile else "-"

    target = int(staff.monthly_target or 0)
    achieved = int(staff.achieved_target or 0)
    achievement = f"{round((achieved / target) * 100, 1)}%" if target else "0%"

    elements = []

    header_left = [
        Paragraph("STAFF PROFILE REPORT", eyebrow_style),
        Paragraph(_report_text(staff.name), name_style),
        Paragraph(
            f"{_report_text(staff.designation)}  \u00b7  {_report_text(staff.emp_code)}",
            sub_style,
        ),
        Spacer(1, 4),
        Paragraph(f"Mobile: {mobile_disp}", sub_style),
        Paragraph(f"Email: {_report_text(staff.email)}", sub_style),
    ]

    photo_cell = ""
    try:
        if staff.profile_photo and staff.profile_photo.path and os.path.exists(staff.profile_photo.path):
            photo_cell = RLImage(staff.profile_photo.path, width=28 * mm, height=28 * mm)
    except Exception:
        photo_cell = ""

    header_tbl = Table(
        [[header_left, photo_cell]],
        colWidths=[doc.width - 34 * mm, 34 * mm],
    )
    header_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _REPORT_PRIMARY),
                ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                ("VALIGN", (1, 0), (1, 0), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 16),
                ("RIGHTPADDING", (0, 0), (-1, -1), 16),
                ("TOPPADDING", (0, 0), (-1, -1), 16),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
            ]
        )
    )
    elements.append(header_tbl)
    elements.append(Spacer(1, 14))

    def add_section(title, pairs):
        elements.append(Paragraph(title, section_style))
        elements.append(
            HRFlowable(width="100%", thickness=1.2, color=_REPORT_LIGHT, spaceBefore=2, spaceAfter=8)
        )
        rows = []
        for i in range(0, len(pairs), 2):
            left = [Paragraph(pairs[i][0].upper(), label_style), Paragraph(_report_text(pairs[i][1]), value_style)]
            if i + 1 < len(pairs):
                right = [Paragraph(pairs[i + 1][0].upper(), label_style), Paragraph(_report_text(pairs[i + 1][1]), value_style)]
            else:
                right = ""
            rows.append([left, right])
        tbl = Table(rows, colWidths=[doc.width / 2.0, doc.width / 2.0])
        tbl.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        elements.append(tbl)
        elements.append(Spacer(1, 8))

    add_section(
        "Employment",
        [
            ("Branch", staff.branch.name if staff.branch_id else "-"),
            ("Role", role_label),
            ("Department", staff.department),
            ("Joining Date", staff.joining_date),
            ("Status", "Active" if staff.is_active else "Inactive"),
        ],
    )

    add_section(
        "Compensation & Performance",
        [
            ("Basic Salary", _report_money(staff.basic_salary)),
            ("Commission Rate", f"{staff.commission_rate}%"),
            ("Monthly Target", target),
            ("Achieved", achieved),
            ("Achievement", achievement),
            ("PF Number", staff.pf_number),
            ("ESI Number", staff.esi_number),
        ],
    )

    add_section(
        "Address",
        [
            ("Street Address", staff.street_address),
            ("City", staff.city),
            ("State", staff.state),
            ("Pincode", staff.pincode),
        ],
    )

    add_section(
        "Bank Details",
        [
            ("Bank Name", staff.bank_name),
            ("Account Number", staff.account_number),
            ("IFSC Code", staff.ifsc_code),
            ("UPI ID", staff.upi_id),
        ],
    )

    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(width="100%", thickness=0.8, color=_REPORT_LIGHT, spaceAfter=6))
    elements.append(
        Paragraph(
            f"Generated on {timezone.localtime().strftime('%d %b %Y, %I:%M %p')}",
            footer_style,
        )
    )

    doc.build(elements)
    return buffer.getvalue()


class StaffViewSet(viewsets.ModelViewSet):
    serializer_class = StaffSerializer
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _manager_branch_code(self):
        user = self.request.user
        if getattr(user, "role", None) != AdminUser.ROLE_BRANCH_MANAGER:
            return None
        return (
            MasterBranch.objects.filter(pk=getattr(user, "branch_id", None))
            .values_list("code", flat=True)
            .first()
        )

    def get_queryset(self):
        # Include deactivated (is_active=False) staff. Soft-deleted stay hidden
        # unless status=inactive so admins can still find them after a mistaken delete.
        qs = (
            StaffProfile.objects.select_related("branch", "admin_user")
            .order_by("-created_at")
        )
        user = self.request.user
        if getattr(user, "role", None) == AdminUser.ROLE_BRANCH_MANAGER:
            manager_code = self._manager_branch_code()
            if manager_code:
                qs = qs.filter(branch__code=manager_code)
            else:
                qs = qs.none()

        search = (self.request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(emp_code__icontains=search)
                | Q(name__icontains=search)
                | Q(designation__icontains=search)
                | Q(branch__name__icontains=search)
            )

        branch_id = self.request.query_params.get("branch_id")
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        status_param = (self.request.query_params.get("status") or "").lower().strip()
        if status_param in {"active"}:
            qs = qs.filter(is_deleted=False, is_active=True)
        elif status_param in {"inactive", "deactivated"}:
            qs = qs.filter(Q(is_active=False) | Q(is_deleted=True))
        else:
            # "all" — show active + deactivated; keep hard soft-deletes out of the default list
            qs = qs.filter(is_deleted=False)

        return qs

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            ser = self.get_serializer(page, many=True)
            paged = self.get_paginated_response(ser.data).data
            return Response({"success": True, "data": paged})
        ser = self.get_serializer(qs, many=True)
        return Response({"success": True, "data": {"results": ser.data}})

    def _deny_if_wrong_branch(self, branch_id):
        user = self.request.user
        if getattr(user, "role", None) == AdminUser.ROLE_BRANCH_MANAGER:
            manager_code = self._manager_branch_code()
            staff_branch_code = (
                StaffProfile.objects.filter(branch_id=branch_id).values_list("branch__code", flat=True).first()
            )
            if not manager_code or manager_code != staff_branch_code:
                return Response(
                    {"success": False, "error": {"code": 403, "message": "Access denied"}},
                    status=status.HTTP_403_FORBIDDEN,
                )
        return None

    def create(self, request, *args, **kwargs):
        requested_role = request.data.get("role") or AdminUser.ROLE_STAFF
        if (
            requested_role == AdminUser.ROLE_BRANCH_MANAGER
            and getattr(request.user, "role", None) != AdminUser.ROLE_ADMIN
        ):
            return Response(
                {"success": False, "error": {"code": 403, "message": "Only admin can create branch manager"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        if getattr(request.user, "role", None) == AdminUser.ROLE_BRANCH_MANAGER:
            branch_id = request.data.get("branch")
            requested_code = (
                Branch.objects.filter(pk=branch_id)
                .values_list("code", flat=True)
                .first()
            )
            manager_code = self._manager_branch_code()
            if not manager_code or manager_code != requested_code:
                return Response(
                    {"success": False, "error": {"code": 403, "message": "Access denied"}},
                    status=status.HTTP_403_FORBIDDEN,
                )

        ser = self.get_serializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        staff = ser.save()
        return Response({"success": True, "data": self.get_serializer(staff).data}, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        staff = self.get_object()
        data = self.get_serializer(staff).data
        target = int(staff.monthly_target or 0)
        achieved = int(staff.achieved_target or 0)
        data["performance"] = {
            "achieved": achieved,
            "target": target,
            "percentage": round((achieved / target) * 100, 2) if target else 0,
        }
        return Response({"success": True, "data": data})

    def partial_update(self, request, *args, **kwargs):
        staff = self.get_object()
        if "branch" in request.data:
            try:
                branch_id = int(request.data.get("branch"))
            except (TypeError, ValueError):
                branch_id = None
            deny = self._deny_if_wrong_branch(branch_id)
            if deny:
                return deny
        ser = self.get_serializer(staff, data=request.data, partial=True, context={"request": request})
        ser.is_valid(raise_exception=True)
        staff = ser.save()
        return Response({"success": True, "data": self.get_serializer(staff).data})

    def destroy(self, request, *args, **kwargs):
        staff = self.get_object()
        release_staff_unique_fields(staff)
        return Response({"success": True}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["patch"], url_path="toggle-status")
    def toggle_status(self, request, pk=None):
        staff = self.get_object()
        staff.is_active = not staff.is_active
        staff.save(update_fields=["is_active", "updated_at"])
        staff.admin_user.is_active = staff.is_active
        staff.admin_user.save(update_fields=["is_active", "updated_at"])
        return Response({"success": True, "status": "active" if staff.is_active else "deactivated"})

    @action(detail=True, methods=["get"], url_path="report")
    def report(self, request, pk=None):
        staff = self.get_object()
        try:
            pdf_bytes = _build_staff_report_pdf(staff)
        except Exception:
            pdf_bytes = _build_simple_pdf(
                [
                    "Staff Performance Report",
                    f"Employee Code: {staff.emp_code}",
                    f"Name: {staff.name}",
                    f"Branch: {staff.branch.name}",
                    f"Designation: {staff.designation}",
                    f"Status: {'Active' if staff.is_active else 'Inactive'}",
                    f"Monthly Target: {staff.monthly_target}",
                    f"Achieved: {staff.achieved_target}",
                    f"Commission %: {staff.commission_rate}",
                    f"Basic Salary: {staff.basic_salary}",
                ]
            )
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{staff.emp_code}_report.pdf"'
        return resp


class BranchStaffListAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if getattr(request.user, "role", None) not in {AdminUser.ROLE_BRANCH_MANAGER, AdminUser.ROLE_ADMIN}:
            return Response(
                {"success": False, "error": {"code": 403, "message": "Access denied"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        qs = StaffProfile.objects.select_related("branch", "admin_user")
        if request.user.role == AdminUser.ROLE_BRANCH_MANAGER:
            manager_code = (
                MasterBranch.objects.filter(pk=getattr(request.user, "branch_id", None))
                .values_list("code", flat=True)
                .first()
            )
            qs = qs.filter(branch__code=manager_code) if manager_code else qs.none()
        elif request.query_params.get("branch_id"):
            qs = qs.filter(branch_id=request.query_params.get("branch_id"))
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(emp_code__icontains=search) | Q(name__icontains=search) | Q(designation__icontains=search))
        status_param = (request.query_params.get("status") or "").lower().strip()
        if status_param == "active":
            qs = qs.filter(is_deleted=False, is_active=True)
        elif status_param in {"inactive", "deactivated"}:
            qs = qs.filter(Q(is_active=False) | Q(is_deleted=True))
        else:
            qs = qs.filter(is_deleted=False)
        ser = StaffSerializer(qs.order_by("-created_at"), many=True)
        return Response({"success": True, "data": {"count": len(ser.data), "results": ser.data}})
