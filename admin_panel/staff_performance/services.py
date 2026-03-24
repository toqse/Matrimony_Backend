"""
Staff performance metrics for branch managers — scoped to a calendar month and branch.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_admin_role
from admin_panel.branch_dashboard.helpers import add_months, month_floor
from admin_panel.branches.models import Branch
from admin_panel.commissions.models import Commission
from admin_panel.enquiries.scoping import admin_branch_for_manager
from admin_panel.staff_mgmt.models import StaffProfile
from master.models import Branch as MasterBranch
from admin_panel.subscriptions.models import CustomerStaffAssignment
from plans.models import Transaction


def _month_range_from_request(request) -> tuple[date | None, date | None, Response | None]:
    """
    Parse ?month=YYYY-MM (optional; default current calendar month).
    Returns (start_inclusive, end_exclusive, error_response).
    """
    raw = (request.query_params.get("month") or "").strip()
    if raw:
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", raw):
            return None, None, Response(
                {
                    "success": False,
                    "error": {
                        "code": 400,
                        "message": "Invalid month format. Use YYYY-MM.",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        y, m = map(int, raw.split("-", 1))
        start = date(y, m, 1)
        end = add_months(start, 1)
    else:
        today = timezone.localdate()
        start = month_floor(today)
        end = add_months(start, 1)
    return start, end, None


def compute_status(achieved: int, target: int) -> str:
    if target <= 0:
        return "Exceeded" if achieved > 0 else "Behind"
    if achieved >= target:
        return "Exceeded"
    if achieved >= target * 0.75:
        return "On Track"
    return "Behind"


def _conversion_rate(subscriptions_sold: int, monthly_target: int) -> float:
    if monthly_target > 0:
        return round(subscriptions_sold / monthly_target * 100.0, 1)
    return round(100.0 if subscriptions_sold > 0 else 0.0, 1)


def branch_manager_scope(request):
    """
    Returns (master_branch_id, admin_branch, error_response).
    - Branch manager: scoped to AdminUser.branch_id; optional ?branch_id= must match.
    - Admin: must pass ?branch_id=<master.Branch pk> to select which branch to analyze.
    """
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return None, None, Response(
            {"success": False, "error": {"code": 401, "message": "Unauthorized"}},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    role = normalize_admin_role(getattr(user, "role", ""))

    if role == AdminUser.ROLE_ADMIN:
        raw = request.query_params.get("branch_id")
        if not raw:
            return None, None, Response(
                {
                    "success": False,
                    "error": {
                        "code": 400,
                        "message": "branch_id is required for admin.",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            master_bid = int(raw)
        except (TypeError, ValueError):
            return None, None, Response(
                {"success": False, "error": {"code": 400, "message": "Invalid branch_id"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not MasterBranch.objects.filter(pk=master_bid, is_active=True).exists():
            return None, None, Response(
                {"success": False, "error": {"code": 400, "message": "Invalid branch_id"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        code = (
            MasterBranch.objects.filter(pk=master_bid).values_list("code", flat=True).first()
        )
        ab = Branch.objects.filter(code=code, is_deleted=False).first() if code else None
        if not ab:
            return None, None, Response(
                {
                    "success": False,
                    "error": {
                        "code": 400,
                        "message": "No admin branch record for this master branch code.",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return master_bid, ab, None

    if role != AdminUser.ROLE_BRANCH_MANAGER:
        return None, None, Response(
            {"success": False, "error": {"code": 403, "message": "Insufficient permissions."}},
            status=status.HTTP_403_FORBIDDEN,
        )
    master_bid = getattr(user, "branch_id", None)
    if not master_bid:
        return None, None, Response(
            {
                "success": False,
                "error": {
                    "code": 400,
                    "message": "No branch assigned to your account. Contact admin.",
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    raw = request.query_params.get("branch_id")
    if raw not in (None, ""):
        try:
            requested = int(raw)
        except (TypeError, ValueError):
            return None, None, Response(
                {"success": False, "error": {"code": 400, "message": "Invalid branch_id"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if requested != master_bid:
            return None, None, Response(
                {"success": False, "error": {"code": 403, "message": "Access denied"}},
                status=status.HTTP_403_FORBIDDEN,
            )

    ab = admin_branch_for_manager(user)
    return master_bid, ab, None


def _staff_queryset(ab, search: str | None):
    qs = StaffProfile.objects.filter(branch=ab, is_deleted=False)
    q = (search or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(emp_code__icontains=q))
    return qs.order_by("name")


def staff_performance_rows(
    master_bid: int,
    ab,
    start: date,
    end: date,
    search: str | None = None,
) -> list[dict]:
    """
    One row per staff member with all table fields (decimal fields as floats for JSON).
    """
    staff_qs = _staff_queryset(ab, search)
    staff_list = list(staff_qs.values("id", "name", "monthly_target"))
    if not staff_list:
        return []

    staff_ids = [s["id"] for s in staff_list]

    profiles_by_staff = {
        r["staff_id"]: r["c"]
        for r in CustomerStaffAssignment.objects.filter(
            staff_id__in=staff_ids,
            user__branch_id=master_bid,
            created_at__date__gte=start,
            created_at__date__lt=end,
        )
        .values("staff_id")
        .annotate(c=Count("id"))
    }

    txn_qs = Transaction.objects.filter(
        payment_status=Transaction.STATUS_SUCCESS,
        transaction_type=Transaction.TYPE_PLAN_PURCHASE,
        user__branch_id=master_bid,
        user__staff_assignment__staff__branch=ab,
        user__staff_assignment__staff_id__in=staff_ids,
        created_at__date__gte=start,
        created_at__date__lt=end,
    )

    subs_by_staff = {
        r["user__staff_assignment__staff_id"]: r["c"]
        for r in txn_qs.values("user__staff_assignment__staff_id").annotate(c=Count("id"))
    }

    rev_by_staff = {
        r["user__staff_assignment__staff_id"]: r["revenue"] or Decimal("0")
        for r in txn_qs.values("user__staff_assignment__staff_id").annotate(
            revenue=Coalesce(Sum("total_amount"), Decimal("0"))
        )
    }

    comm_qs = Commission.objects.filter(
        branch=ab,
        staff_id__in=staff_ids,
        status__in=[Commission.STATUS_APPROVED, Commission.STATUS_PAID],
        created_at__date__gte=start,
        created_at__date__lt=end,
    )
    comm_by_staff = {
        r["staff_id"]: r["c"] or Decimal("0")
        for r in comm_qs.values("staff_id").annotate(c=Coalesce(Sum("commission_amt"), Decimal("0")))
    }

    rows: list[dict] = []
    for s in staff_list:
        sid = s["id"]
        target = int(s["monthly_target"] or 0)
        profiles_created = int(profiles_by_staff.get(sid, 0))
        subscriptions_sold = int(subs_by_staff.get(sid, 0))
        revenue = rev_by_staff.get(sid) or Decimal("0")
        commission_earned = comm_by_staff.get(sid) or Decimal("0")
        conversion_rate = _conversion_rate(subscriptions_sold, target)
        achieved = subscriptions_sold
        status = compute_status(achieved, target)
        rows.append(
            {
                "staff_id": sid,
                "staff_name": s["name"],
                "profiles_created": profiles_created,
                "subscriptions_sold": subscriptions_sold,
                "revenue": float(revenue),
                "commission_earned": float(commission_earned),
                "conversion_rate": conversion_rate,
                "target": target,
                "achieved": achieved,
                "status": status,
            }
        )
    return rows


def summary_kpis(master_bid: int, ab, start: date, end: date) -> dict:
    """
    Branch-level KPIs for the month (not per staff).
    """
    total_profiles = CustomerStaffAssignment.objects.filter(
        staff__branch=ab,
        user__branch_id=master_bid,
        created_at__date__gte=start,
        created_at__date__lt=end,
    ).count()

    subs_qs = Transaction.objects.filter(
        payment_status=Transaction.STATUS_SUCCESS,
        transaction_type=Transaction.TYPE_PLAN_PURCHASE,
        user__branch_id=master_bid,
        created_at__date__gte=start,
        created_at__date__lt=end,
    )
    subscriptions_sold = subs_qs.count()
    branch_revenue = subs_qs.aggregate(v=Coalesce(Sum("total_amount"), Decimal("0")))["v"] or Decimal("0")

    rows = staff_performance_rows(master_bid, ab, start, end, search=None)
    rates = []
    for r in rows:
        t = r["target"]
        if t > 0:
            rates.append(r["subscriptions_sold"] / t * 100.0)
        elif r["subscriptions_sold"] > 0:
            rates.append(100.0)
    avg_conversion = round(sum(rates) / len(rates), 1) if rates else 0.0

    return {
        "total_profiles_created": total_profiles,
        "subscriptions_sold": subscriptions_sold,
        "branch_revenue": float(branch_revenue),
        "avg_conversion_rate": avg_conversion,
        "month": f"{start.year:04d}-{start.month:02d}",
    }
