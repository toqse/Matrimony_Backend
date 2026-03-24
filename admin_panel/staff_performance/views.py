"""
Staff Performance APIs — branch_manager only; scoped to manager's branch and calendar month.
"""
from __future__ import annotations

import csv
from io import StringIO

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.pagination import StandardPagination

from .services import (
    _month_range_from_request,
    branch_manager_scope,
    staff_performance_rows,
    summary_kpis,
)


def _table_row_public(row: dict) -> dict:
    """Detailed table fields (no staff_id)."""
    return {
        "staff_name": row["staff_name"],
        "profiles_created": row["profiles_created"],
        "subscriptions_sold": row["subscriptions_sold"],
        "revenue": row["revenue"],
        "commission_earned": row["commission_earned"],
        "conversion_rate": row["conversion_rate"],
        "target": row["target"],
        "achieved": row["achieved"],
        "status": row["status"],
    }


class StaffPerformanceSummaryView(APIView):
    """GET /api/v1/branch/staff-performance/summary/ — KPI cards."""

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        master_bid, ab, err = branch_manager_scope(request)
        if err:
            return err
        if not ab:
            return Response(
                {
                    "success": True,
                    "data": {
                        "total_profiles_created": 0,
                        "subscriptions_sold": 0,
                        "branch_revenue": 0.0,
                        "avg_conversion_rate": 0.0,
                        "month": None,
                    },
                }
            )
        start, end, err_m = _month_range_from_request(request)
        if err_m:
            return err_m
        data = summary_kpis(master_bid, ab, start, end)
        return Response({"success": True, "data": data})


class StaffPerformanceChartView(APIView):
    """GET /api/v1/branch/staff-performance/chart/ — revenue + commission per staff."""

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        master_bid, ab, err = branch_manager_scope(request)
        if err:
            return err
        if not ab:
            return Response({"success": True, "data": {"staff": [], "month": None}})
        start, end, err_m = _month_range_from_request(request)
        if err_m:
            return err_m
        rows = staff_performance_rows(master_bid, ab, start, end, search=None)
        staff = [
            {
                "staff_id": r["staff_id"],
                "staff_name": r["staff_name"],
                "revenue": r["revenue"],
                "commission": r["commission_earned"],
            }
            for r in rows
        ]
        return Response(
            {
                "success": True,
                "data": {
                    "month": f"{start.year:04d}-{start.month:02d}",
                    "staff": staff,
                },
            }
        )


class StaffPerformanceTargetsView(APIView):
    """GET /api/v1/branch/staff-performance/targets/ — target vs achieved (subscriptions) per staff."""

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        master_bid, ab, err = branch_manager_scope(request)
        if err:
            return err
        if not ab:
            return Response({"success": True, "data": {"staff": [], "month": None}})
        start, end, err_m = _month_range_from_request(request)
        if err_m:
            return err_m
        rows = staff_performance_rows(master_bid, ab, start, end, search=None)
        staff = [
            {
                "staff_id": r["staff_id"],
                "staff_name": r["staff_name"],
                "target": r["target"],
                "achieved": r["achieved"],
            }
            for r in rows
        ]
        return Response(
            {
                "success": True,
                "data": {
                    "month": f"{start.year:04d}-{start.month:02d}",
                    "staff": staff,
                },
            }
        )


class StaffPerformanceListView(APIView):
    """GET /api/v1/branch/staff-performance/ — paginated detailed table."""

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        master_bid, ab, err = branch_manager_scope(request)
        if err:
            return err
        if not ab:
            return Response(
                {
                    "success": True,
                    "data": {
                        "month": None,
                        "count": 0,
                        "next": None,
                        "previous": None,
                        "results": [],
                    },
                }
            )
        start, end, err_m = _month_range_from_request(request)
        if err_m:
            return err_m
        search = (request.query_params.get("search") or "").strip() or None
        rows = staff_performance_rows(master_bid, ab, start, end, search=search)
        table_rows = [_table_row_public(r) for r in rows]
        paginator = StandardPagination()
        page = paginator.paginate_queryset(table_rows, request)
        if page is not None:
            return Response(
                {
                    "success": True,
                    "data": {
                        "month": f"{start.year:04d}-{start.month:02d}",
                        "count": paginator.page.paginator.count,
                        "next": paginator.get_next_link(),
                        "previous": paginator.get_previous_link(),
                        "results": page,
                    },
                }
            )
        return Response(
            {
                "success": True,
                "data": {
                    "month": f"{start.year:04d}-{start.month:02d}",
                    "count": len(table_rows),
                    "next": None,
                    "previous": None,
                    "results": table_rows,
                },
            }
        )


class StaffPerformanceExportView(APIView):
    """GET /api/v1/branch/staff-performance/export/ — CSV of detailed table (same filters as list)."""

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        master_bid, ab, err = branch_manager_scope(request)
        if err:
            return err
        if not ab:
            response = HttpResponse("\ufeff", content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="staff_performance_export.csv"'
            return response
        start, end, err_m = _month_range_from_request(request)
        if err_m:
            return err_m
        search = (request.query_params.get("search") or "").strip() or None
        rows = staff_performance_rows(master_bid, ab, start, end, search=search)
        table_rows = [_table_row_public(r) for r in rows]

        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "Staff Name",
                "Profiles Created",
                "Subscriptions Sold",
                "Revenue",
                "Commission Earned",
                "Conversion Rate %",
                "Target",
                "Achieved",
                "Status",
            ]
        )
        for r in table_rows:
            writer.writerow(
                [
                    r["staff_name"],
                    r["profiles_created"],
                    r["subscriptions_sold"],
                    r["revenue"],
                    r["commission_earned"],
                    r["conversion_rate"],
                    r["target"],
                    r["achieved"],
                    r["status"],
                ]
            )

        response = HttpResponse("\ufeff" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="staff_performance_export.csv"'
        return response
