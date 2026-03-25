from __future__ import annotations

import csv
from decimal import Decimal
from io import BytesIO, StringIO

from django.db.models import Case, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_admin_role
from admin_panel.commissions.models import Commission
from admin_panel.staff_dashboard.services import staff_profile_for_dashboard

from .pagination import StaffCommissionPagination
from .serializers import StaffCommissionDetailSerializer, StaffCommissionListSerializer, plan_display_name


READ_ONLY_MSG = "Commission records are read-only."
INVALID_STATUS_MSG = "Invalid status. Must be: pending, approved, paid, cancelled."
INVALID_FORMAT_MSG = "Invalid format. Use ?format=pdf or ?format=csv."
NOT_FOUND_MSG = "Commission record not found."

VALID_STATUSES = frozenset(
    {
        Commission.STATUS_PENDING,
        Commission.STATUS_APPROVED,
        Commission.STATUS_PAID,
        Commission.STATUS_CANCELLED,
    }
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


def _resolve_staff(request):
    user = request.user
    role = normalize_admin_role(getattr(user, "role", ""))
    if role != AdminUser.ROLE_STAFF:
        return None, Response(
            {
                "success": False,
                "error": {"code": 403, "message": "Access denied. Staff token required."},
            },
            status=403,
        )
    if not getattr(user, "is_active", True):
        return None, Response(
            {
                "success": False,
                "error": {"code": 403, "message": "Your account has been deactivated. Contact admin."},
            },
            status=403,
        )
    staff = staff_profile_for_dashboard(user)
    if not staff:
        return None, Response(
            {
                "success": False,
                "error": {"code": 400, "message": "Staff profile not configured. Contact admin."},
            },
            status=400,
        )
    if not staff.is_active:
        return None, Response(
            {
                "success": False,
                "error": {"code": 403, "message": "Your account has been deactivated. Contact admin."},
            },
            status=403,
        )
    return staff, None


def _staff_commission_queryset(staff):
    return Commission.objects.select_related(
        "customer", "subscription", "subscription__plan", "plan"
    ).filter(staff=staff)


def _apply_list_filters(qs, request):
    raw_status = (request.query_params.get("status") or "").strip().lower()
    if raw_status:
        if raw_status not in VALID_STATUSES:
            return None, Response(
                {"success": False, "error": {"code": 400, "message": INVALID_STATUS_MSG}},
                status=400,
            )
        qs = qs.filter(status=raw_status)

    plan_raw = request.query_params.get("plan_id")
    if plan_raw not in (None, ""):
        try:
            pid = int(plan_raw)
        except (TypeError, ValueError):
            return None, Response(
                {"success": False, "error": {"code": 400, "message": "Invalid plan_id"}},
                status=400,
            )
        qs = qs.filter(Q(plan_id=pid) | Q(subscription__plan_id=pid))

    search = (request.query_params.get("search") or "").strip()
    if search:
        qs = qs.filter(
            Q(customer__name__icontains=search) | Q(customer__matri_id__icontains=search)
        )

    return qs, None


def _summary_data(qs):
    _dec = DecimalField(max_digits=12, decimal_places=2)
    _z = Value(Decimal("0"), output_field=_dec)
    row = qs.aggregate(
        pending=Coalesce(
            Sum(
                Case(
                    When(status=Commission.STATUS_PENDING, then=F("commission_amt")),
                    default=_z,
                    output_field=_dec,
                )
            ),
            _z,
        ),
        approved=Coalesce(
            Sum(
                Case(
                    When(status=Commission.STATUS_APPROVED, then=F("commission_amt")),
                    default=_z,
                    output_field=_dec,
                )
            ),
            _z,
        ),
        paid=Coalesce(
            Sum(
                Case(
                    When(status=Commission.STATUS_PAID, then=F("commission_amt")),
                    default=_z,
                    output_field=_dec,
                )
            ),
            _z,
        ),
        total=Coalesce(Sum("commission_amt"), _z),
    )
    return {
        "pending": float(row["pending"] or 0),
        "approved": float(row["approved"] or 0),
        "paid": float(row["paid"] or 0),
        "total": float(row["total"] or 0),
    }


class StaffCommissionReadOnlyAPIView(APIView):
    """Reject mutations with 403 (not 405)."""

    def post(self, request, *args, **kwargs):
        return Response(
            {"success": False, "error": {"code": 403, "message": READ_ONLY_MSG}},
            status=403,
        )

    def put(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)


class StaffMyCommissionsSummaryAPIView(StaffCommissionReadOnlyAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        staff, err = _resolve_staff(request)
        if err:
            return err
        qs = _staff_commission_queryset(staff)
        return Response({"success": True, "data": _summary_data(qs)})


class StaffMyCommissionsListAPIView(StaffCommissionReadOnlyAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        staff, err = _resolve_staff(request)
        if err:
            return err
        qs = _staff_commission_queryset(staff)
        qs, ferr = _apply_list_filters(qs, request)
        if ferr:
            return ferr
        qs = qs.order_by("-created_at")
        paginator = StaffCommissionPagination()
        page = paginator.paginate_queryset(qs, request)
        ser = StaffCommissionListSerializer(page if page is not None else qs, many=True)
        if page is not None:
            body = paginator.get_paginated_response(ser.data).data
            return Response({"success": True, "data": body})
        return Response({"success": True, "data": {"count": len(ser.data), "results": ser.data}})


class StaffMyCommissionDetailAPIView(StaffCommissionReadOnlyAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        staff, err = _resolve_staff(request)
        if err:
            return err
        obj = _staff_commission_queryset(staff).filter(pk=pk).first()
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": NOT_FOUND_MSG}},
                status=404,
            )
        return Response({"success": True, "data": StaffCommissionDetailSerializer(obj).data})


class StaffMyCommissionsExportAPIView(StaffCommissionReadOnlyAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        staff, err = _resolve_staff(request)
        if err:
            return err
        fmt = (request.query_params.get("format") or "").strip().lower()
        if fmt not in ("pdf", "csv"):
            return Response(
                {"success": False, "error": {"code": 400, "message": INVALID_FORMAT_MSG}},
                status=400,
            )
        qs = _staff_commission_queryset(staff)
        qs, ferr = _apply_list_filters(qs, request)
        if ferr:
            return ferr
        qs = qs.order_by("-created_at")

        if fmt == "csv":
            buf = StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                ["Date", "Customer", "Matri ID", "Plan", "Sale Amount", "Rate %", "Commission", "Status"]
            )
            for row in qs.iterator(chunk_size=200):
                writer.writerow(
                    [
                        row.created_at.date().isoformat() if row.created_at else "",
                        row.customer.name or "",
                        row.customer.matri_id or "",
                        plan_display_name(row),
                        str(row.sale_amount or 0),
                        str(row.commission_rate or 0),
                        str(row.commission_amt or 0),
                        row.status,
                    ]
                )
            resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
            resp["Content-Disposition"] = 'attachment; filename="my_commissions.csv"'
            return resp

        lines = ["My Commissions — export"]
        max_rows = 80
        n = 0
        for row in qs.iterator(chunk_size=200):
            n += 1
            if n > max_rows:
                lines.append(f"... and more (truncated after {max_rows} rows). Use CSV for full export.")
                break
            lines.append(
                f"{row.created_at.date() if row.created_at else ''} | {row.customer.name or ''} | "
                f"{plan_display_name(row)} | ₹{row.sale_amount} | {row.commission_rate}% | "
                f"₹{row.commission_amt} | {row.status}"
            )
        pdf = _build_simple_pdf(lines)
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = 'attachment; filename="my_commissions.pdf"'
        return resp
