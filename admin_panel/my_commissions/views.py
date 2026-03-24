from __future__ import annotations

import csv
from decimal import Decimal
from io import StringIO

from django.db.models import Case, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.commissions.models import Commission
from admin_panel.commissions.serializers import _plan_display_name
from admin_panel.commissions.views import (
    _branch_manager_code_or_error,
    _build_simple_pdf,
    _staff_profile_for_admin_user,
)
from admin_panel.pagination import StandardPagination
from admin_panel.permissions import IsBranchManagerOnly


def _resolve_manager_staff_profile(request):
    """
    Branch Manager's own StaffProfile (mobile match), scoped to their master branch code.
    Returns (StaffProfile | None, Response | None). None profile => empty lists / zero KPIs.
    """
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


def _commission_row(c: Commission) -> dict:
    return {
        "id": c.id,
        "date": c.created_at.date().isoformat() if c.created_at else None,
        "customer": c.customer.name or "",
        "plan": _plan_display_name(c),
        "sale_amount": float(c.sale_amount or 0),
        "rate": float(c.commission_rate or 0),
        "commission": float(c.commission_amt or 0),
        "status": c.status,
    }


def _apply_my_commission_filters(request, qs):
    status_filter = (request.query_params.get("status") or "").strip().lower()
    if status_filter and status_filter not in {
        Commission.STATUS_PENDING,
        Commission.STATUS_APPROVED,
        Commission.STATUS_PAID,
        Commission.STATUS_CANCELLED,
    }:
        return None, Response(
            {"success": False, "error": {"code": 400, "message": "Invalid status filter."}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if status_filter:
        qs = qs.filter(status=status_filter)

    plan_id = (request.query_params.get("plan_id") or "").strip()
    if plan_id:
        try:
            pid = int(plan_id)
        except (TypeError, ValueError):
            return None, Response(
                {"success": False, "error": {"code": 400, "message": "Invalid plan_id"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = qs.filter(Q(subscription__plan_id=pid) | Q(plan_id=pid))

    search = (request.query_params.get("search") or "").strip()
    if search:
        qs = qs.filter(
            Q(customer__name__icontains=search) | Q(customer__matri_id__icontains=search)
        )

    return qs, None


class MyCommissionsSummaryView(APIView):
    """KPI cards for the logged-in Branch Manager's own commissions only."""

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
                        "pending": 0.0,
                        "approved": 0.0,
                        "paid": 0.0,
                        "total": 0.0,
                    },
                }
            )

        qs = Commission.objects.filter(staff=sp)
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
        return Response(
            {
                "success": True,
                "data": {
                    "pending": float(row["pending"] or 0),
                    "approved": float(row["approved"] or 0),
                    "paid": float(row["paid"] or 0),
                    "total": float(row["total"] or 0),
                },
            }
        )


class MyCommissionsListView(APIView):
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

        qs = Commission.objects.filter(staff=sp).select_related(
            "customer", "subscription", "subscription__plan", "plan"
        )
        qs, ferr = _apply_my_commission_filters(request, qs)
        if ferr:
            return ferr

        qs = qs.order_by("-created_at")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        rows = [_commission_row(c) for c in page]
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


class MyCommissionDetailView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManagerOnly]

    def get(self, request, pk):
        sp, err = _resolve_manager_staff_profile(request)
        if err:
            return err
        if sp is None:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Commission not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        c = (
            Commission.objects.filter(pk=pk, staff=sp)
            .select_related("customer", "subscription", "subscription__plan", "plan")
            .first()
        )
        if not c:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Commission not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"success": True, "data": _commission_row(c)})


class MyCommissionsExportView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManagerOnly]

    def get(self, request):
        fmt = (request.query_params.get("format") or "").strip().lower()
        if fmt not in ("pdf", "csv"):
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Invalid export format. Use pdf or csv."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        sp, err = _resolve_manager_staff_profile(request)
        if err:
            return err
        if sp is None:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "No staff profile linked to your account."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = Commission.objects.filter(staff=sp).select_related(
            "customer", "subscription", "subscription__plan", "plan"
        )
        qs, ferr = _apply_my_commission_filters(request, qs)
        if ferr:
            return ferr
        qs = qs.order_by("-created_at")
        rows = list(qs)

        if fmt == "csv":
            buf = StringIO()
            w = csv.writer(buf)
            w.writerow(
                ["id", "date", "customer", "plan", "sale_amount", "rate", "commission", "status"]
            )
            for c in rows:
                w.writerow(
                    [
                        c.id,
                        c.created_at.date().isoformat() if c.created_at else "",
                        c.customer.name or "",
                        _plan_display_name(c),
                        str(c.sale_amount),
                        str(c.commission_rate),
                        str(c.commission_amt),
                        c.status,
                    ]
                )
            resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
            resp["Content-Disposition"] = (
                f'attachment; filename="my_commissions_{timezone.localdate().isoformat()}.csv"'
            )
            return resp

        lines = [
            f"My Commissions — {sp.name} ({sp.emp_code})",
            f"Exported: {timezone.localdate().isoformat()}",
            "",
        ]
        for c in rows:
            lines.extend(
                [
                    f"ID {c.id} | {c.created_at.date() if c.created_at else '-'}",
                    f"Customer: {c.customer.name} ({c.customer.matri_id})",
                    f"Plan: {_plan_display_name(c)}",
                    f"Sale: {c.sale_amount} | Rate: {c.commission_rate}% | Commission: {c.commission_amt}",
                    f"Status: {c.status}",
                    "---",
                ]
            )
        pdf = _build_simple_pdf(lines)
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = (
            f'attachment; filename="my_commissions_{timezone.localdate().isoformat()}.pdf"'
        )
        return resp
