from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_admin_role
from admin_panel.payroll.models import SalaryRecord
from admin_panel.payroll.views import _build_simple_pdf
from admin_panel.staff_dashboard.services import staff_profile_for_dashboard

from .pagination import StaffSalaryPagination
from .serializers import StaffSalaryHistorySerializer

READ_ONLY_MSG = "Salary records are read-only."
INVALID_YEAR_MSG = "Invalid year. Use a 4-digit year e.g. 2026."
NOT_FOUND_MSG = "Salary record not found."
SLIP_NOT_ALLOWED_MSG = "Salary slip available only for approved or paid records."


def _money_int(d: Decimal | float | int | None) -> int:
    if d is None:
        return 0
    if isinstance(d, Decimal):
        return int(d)
    return int(Decimal(str(d)))


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


def _staff_salary_qs(staff):
    return SalaryRecord.objects.select_related("staff", "branch").filter(staff=staff)


class StaffSalaryReadOnlyAPIView(APIView):
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


class StaffSalarySummaryAPIView(StaffSalaryReadOnlyAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        staff, err = _resolve_staff(request)
        if err:
            return err
        today = timezone.localdate()
        qs = _staff_salary_qs(staff).filter(month__year=today.year)
        agg = qs.aggregate(
            ytd_gross=Sum("gross"),
            ytd_commission=Sum("commission"),
            ytd_net=Sum("net"),
        )
        return Response(
            {
                "success": True,
                "data": {
                    "ytd_gross_pay": _money_int(agg["ytd_gross"]),
                    "ytd_commission": _money_int(agg["ytd_commission"]),
                    "ytd_net_pay": _money_int(agg["ytd_net"]),
                    "records_count": qs.count(),
                },
            }
        )


class StaffSalaryCurrentAPIView(StaffSalaryReadOnlyAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        staff, err = _resolve_staff(request)
        if err:
            return err
        today = timezone.localdate()
        cur_first = date(today.year, today.month, 1)
        month_label = cur_first.strftime("%B %Y")
        rec = _staff_salary_qs(staff).filter(month=cur_first).first()
        if not rec:
            return Response(
                {
                    "success": True,
                    "data": {
                        "month": month_label,
                        "basic": 0,
                        "commission_approved": 0,
                        "allowances": 0,
                        "deductions": 0,
                        "gross": 0,
                        "net_pay": 0,
                        "status": None,
                    },
                }
            )
        return Response(
            {
                "success": True,
                "data": {
                    "month": month_label,
                    "basic": _money_int(rec.basic),
                    "commission_approved": _money_int(rec.commission),
                    "allowances": _money_int(rec.allowances),
                    "deductions": _money_int(rec.deductions),
                    "gross": _money_int(rec.gross),
                    "net_pay": _money_int(rec.net),
                    "status": rec.status,
                },
            }
        )


class StaffSalaryHistoryListAPIView(StaffSalaryReadOnlyAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        staff, err = _resolve_staff(request)
        if err:
            return err
        qs = _staff_salary_qs(staff)
        raw_year = request.query_params.get("year")
        if raw_year is not None and str(raw_year).strip() != "":
            ys = str(raw_year).strip()
            if not re.fullmatch(r"\d{4}", ys):
                return Response(
                    {"success": False, "error": {"code": 400, "message": INVALID_YEAR_MSG}},
                    status=400,
                )
            try:
                y = int(ys)
            except ValueError:
                return Response(
                    {"success": False, "error": {"code": 400, "message": INVALID_YEAR_MSG}},
                    status=400,
                )
            if y < 1900 or y > 2100:
                return Response(
                    {"success": False, "error": {"code": 400, "message": INVALID_YEAR_MSG}},
                    status=400,
                )
            qs = qs.filter(month__year=y)
        qs = qs.order_by("-month", "-id")
        paginator = StaffSalaryPagination()
        page = paginator.paginate_queryset(qs, request)
        ser = StaffSalaryHistorySerializer(
            page if page is not None else qs,
            many=True,
            context={"request": request},
        )
        if page is not None:
            return Response({"success": True, "data": paginator.get_paginated_response(ser.data).data})
        return Response({"success": True, "data": {"count": len(ser.data), "results": ser.data}})


class StaffSalaryDownloadAPIView(StaffSalaryReadOnlyAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        staff, err = _resolve_staff(request)
        if err:
            return err
        obj = _staff_salary_qs(staff).filter(pk=pk).first()
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": NOT_FOUND_MSG}},
                status=404,
            )
        if obj.status not in (SalaryRecord.STATUS_APPROVED, SalaryRecord.STATUS_PAID):
            return Response(
                {"success": False, "error": {"code": 400, "message": SLIP_NOT_ALLOWED_MSG}},
                status=400,
            )
        month_label = obj.month.strftime("%B %Y") if obj.month else ""
        lines = [
            "Salary Slip",
            f"Staff: {obj.staff.name} ({obj.staff.emp_code})",
            f"Branch: {obj.branch.name}",
            f"Month: {month_label}",
            f"Basic: {obj.basic}",
            f"Commission: {obj.commission}",
            f"Allowances: {obj.allowances}",
            f"Deductions: {obj.deductions}",
            f"Gross: {obj.gross}",
            f"Net: {obj.net}",
            f"Status: {obj.status}",
        ]
        pdf = _build_simple_pdf(lines)
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="salary_{obj.id}_slip.pdf"'
        return resp
