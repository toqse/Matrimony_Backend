from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_admin_role
from admin_panel.enquiries.scoping import admin_branch_for_manager


def month_floor(d: date) -> date:
    return date(d.year, d.month, 1)


def add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, 1)


def last_12_months_inclusive(today: date) -> list[date]:
    end = month_floor(today)
    start = add_months(end, -11)
    return [add_months(start, i) for i in range(12)]


def pct_change(current: float, previous: float) -> float:
    if previous <= 0:
        return round(100.0 if current > 0 else 0.0, 1)
    return round((current - previous) / previous * 100.0, 1)


def branch_manager_context(request) -> tuple[int | None, Response | None]:
    """
    Returns (master_branch_id, error_response).
    master_branch_id is AdminUser.branch_id (master.Branch PK).
    """
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return None, Response(
            {"success": False, "error": {"code": 401, "message": "Unauthorized"}},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    role = normalize_admin_role(getattr(user, "role", ""))
    if role != AdminUser.ROLE_BRANCH_MANAGER:
        return None, Response(
            {"success": False, "error": {"code": 403, "message": "Access denied"}},
            status=status.HTTP_403_FORBIDDEN,
        )
    master_bid = getattr(user, "branch_id", None)
    if not master_bid:
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

    raw = request.query_params.get("branch_id")
    if raw not in (None, ""):
        try:
            requested = int(raw)
        except (TypeError, ValueError):
            return None, Response(
                {"success": False, "error": {"code": 400, "message": "Invalid branch_id"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if requested != master_bid:
            return None, Response(
                {"success": False, "error": {"code": 403, "message": "Access denied"}},
                status=status.HTTP_403_FORBIDDEN,
            )

    return master_bid, None


def admin_branch_for_request(request):
    user = request.user
    return admin_branch_for_manager(user)


def calendar_month_bounds(today: date | None = None):
    today = today or timezone.localdate()
    cur_start = month_floor(today)
    next_start = add_months(cur_start, 1)
    prev_start = add_months(cur_start, -1)
    return cur_start, next_start, prev_start


def decimal_to_float(v: Decimal | None) -> float:
    if v is None:
        return 0.0
    return float(v)
