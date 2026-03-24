from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.commissions.models import Commission
from admin_panel.commissions.views import (
    _branch_manager_code_or_error,
    _build_simple_pdf,
    _staff_profile_for_admin_user,
)
from admin_panel.pagination import StandardPagination
from admin_panel.payroll.models import SalaryRecord
from admin_panel.payroll.views import month_paid_at_bounds
from admin_panel.permissions import IsBranchManagerOnly

_READ_ONLY = Response(
    {
        "success": False,
        "error": {"code": 403, "message": "Salary records are read-only."},
    },
    status=status.HTTP_403_FORBIDDEN,
)


class MySalaryReadOnlyMixin:
    def post(self, request, *args, **kwargs):
        return _READ_ONLY

    def put(self, request, *args, **kwargs):
        return _READ_ONLY

    def patch(self, request, *args, **kwargs):
        return _READ_ONLY

    def delete(self, request, *args, **kwargs):
        return _READ_ONLY


def _resolve_manager_staff_profile(request):
    code, err = _branch_manager_code_or_error(request)
    if err:
        return None, err
    sp = _staff_profile_for_admin_user(request.user)
    if not sp:
        return None, None
    if sp.branch.code != code:
        return None, Response(
            {"success": False, "error": {"code": 403, "message": "Access denied"}},
            status=status.HTTP_403_FORBIDDEN,
        )
    return sp, None


def _ytd_bounds():
    today = timezone.localdate()
    start = date(today.year, 1, 1)
    end_month = date(today.year, today.month, 1)
    return start, end_month


def _salary_qs_for_manager(sp):
    return SalaryRecord.objects.filter(staff=sp)


def _commission_approved_in_month(staff_id: int, month_start: date) -> Decimal:
    start, end_ex = month_paid_at_bounds(month_start)
    total = Commission.objects.filter(
        staff_id=staff_id,
        status=Commission.STATUS_APPROVED,
        updated_at__gte=start,
        updated_at__lt=end_ex,
    ).aggregate(t=Sum("commission_amt"))["t"]
    return Decimal(total or 0)


def _parse_year_param(raw: str | None):
    if raw is None:
        return None, None
    s = (raw or "").strip()
    if not s:
        return None, None
    if not re.fullmatch(r"\d{4}", s):
        return None, "Invalid year format."
    return int(s), None


def _my_salary_download_url(request, pk: int) -> str:
    if not request:
        return ""
    path = reverse("my-salary-download", kwargs={"pk": pk})
    return request.build_absolute_uri(path)


def _row_dict(request, obj: SalaryRecord) -> dict:
    m = obj.month
    download_url = _my_salary_download_url(request, obj.pk)
    deductions = float(obj.deductions or 0)
    return {
        "id": obj.id,
        "month": m.strftime("%B") if m else None,
        "year": m.year if m else None,
        "basic": float(obj.basic or 0),
        "commission": float(obj.commission or 0),
        "allowances": float(obj.allowances or 0),
        "deductions": deductions,
        "dections": deductions,
        "gross": float(obj.gross or 0),
        "net": float(obj.net or 0),
        "status": obj.status,
        "download_url": download_url,
        "download": download_url,
    }


class MySalarySummaryView(MySalaryReadOnlyMixin, APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManagerOnly]

    def get(self, request):
        sp, err = _resolve_manager_staff_profile(request)
        if err:
            return err
        if sp is None:
            return Response(
                {
                    "success": True,
                    "data": {
                        "ytd_gross_pay": 0,
                        "ytd_commission": 0,
                        "ytd_net_pay": 0,
                        "records_count": 0,
                    },
                }
            )
        y0, y1 = _ytd_bounds()
        qs = _salary_qs_for_manager(sp).filter(month__gte=y0, month__lte=y1)
        agg = qs.aggregate(
            ytd_gross=Sum("gross"),
            ytd_commission=Sum("commission"),
            ytd_net=Sum("net"),
        )
        return Response(
            {
                "success": True,
                "data": {
                    "ytd_gross_pay": float(agg["ytd_gross"] or 0),
                    "ytd_commission": float(agg["ytd_commission"] or 0),
                    "ytd_net_pay": float(agg["ytd_net"] or 0),
                    "records_count": qs.count(),
                },
            }
        )


class MySalaryCurrentView(MySalaryReadOnlyMixin, APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManagerOnly]

    def get(self, request):
        sp, err = _resolve_manager_staff_profile(request)
        if err:
            return err
        if sp is None:
            return Response({"success": True, "data": None})
        obj = _salary_qs_for_manager(sp).order_by("-month", "-id").first()
        if not obj:
            return Response({"success": True, "data": None})
        m = obj.month
        month_label = m.strftime("%B %Y") if m else ""
        cap = _commission_approved_in_month(sp.id, m) if m else Decimal(0)
        return Response(
            {
                "success": True,
                "data": {
                    "month": month_label,
                    "basic": float(obj.basic or 0),
                    "commission_approved": float(cap),
                    "allowances": float(obj.allowances or 0),
                    "deductions": float(obj.deductions or 0),
                    "dections": float(obj.deductions or 0),
                    "gross": float(obj.gross or 0),
                    "net_pay": float(obj.net or 0),
                    "net": float(obj.net or 0),
                    "status": obj.status,
                },
            }
        )


class MySalaryListView(MySalaryReadOnlyMixin, APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManagerOnly]

    def get(self, request):
        sp, err = _resolve_manager_staff_profile(request)
        if err:
            return err
        if sp is None:
            return Response(
                {
                    "success": True,
                    "data": {
                        "count": 0,
                        "next": None,
                        "previous": None,
                        "results": [],
                    },
                }
            )
        y_raw = request.query_params.get("year")
        year, yerr = _parse_year_param(y_raw)
        if yerr:
            return Response(
                {"success": False, "error": {"code": 400, "message": yerr}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = _salary_qs_for_manager(sp).order_by("-month", "-id")
        if year is not None:
            qs = qs.filter(month__year=year)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        rows = [_row_dict(request, o) for o in page]
        return Response(
            {
                "success": True,
                "data": {
                    "count": paginator.page.paginator.count,
                    "next": paginator.get_next_link(),
                    "previous": paginator.get_previous_link(),
                    "results": rows,
                },
            }
        )


class MySalaryDownloadView(MySalaryReadOnlyMixin, APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManagerOnly]

    def get(self, request, pk):
        sp, err = _resolve_manager_staff_profile(request)
        if err:
            return err
        if sp is None:
            return Response(
                {
                    "success": False,
                    "error": {"code": 404, "message": "Salary record not found."},
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        obj = SalaryRecord.objects.filter(pk=pk, staff=sp).select_related("staff", "branch").first()
        if not obj:
            return Response(
                {
                    "success": False,
                    "error": {"code": 404, "message": "Salary record not found."},
                },
                status=status.HTTP_404_NOT_FOUND,
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
