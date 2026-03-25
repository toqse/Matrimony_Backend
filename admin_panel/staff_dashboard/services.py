"""Staff dashboard KPI helpers (scoped to one StaffProfile)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.response import Response

from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_admin_role
from admin_panel.commissions.models import Commission
from admin_panel.staff_mgmt.models import StaffProfile
from admin_panel.subscriptions.models import CustomerStaffAssignment
from plans.models import Transaction


def _month_floor(d: date) -> date:
    return date(d.year, d.month, 1)


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, 1)


def _growth_percent(current: Decimal, previous: Decimal) -> float:
    if previous <= 0:
        return 100.0 if current > 0 else 0.0
    return round(float((current - previous) / previous * 100.0), 1)


def resolve_staff_dashboard_request(request):
    """
    Returns (staff_profile, None) on success, or (None, Response) on failure.
    Order: role → user active → staff row → staff.active
    """
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
                "error": {
                    "code": 403,
                    "message": "Your account has been deactivated. Contact admin.",
                },
            },
            status=403,
        )
    staff = staff_profile_for_dashboard(user)
    if not staff:
        return None, Response(
            {
                "success": False,
                "error": {
                    "code": 400,
                    "message": "Staff profile not configured. Contact admin.",
                },
            },
            status=400,
        )
    if not staff.is_active:
        return None, Response(
            {
                "success": False,
                "error": {
                    "code": 403,
                    "message": "Your account has been deactivated. Contact admin.",
                },
            },
            status=403,
        )
    return staff, None


def staff_profile_for_dashboard(user) -> StaffProfile | None:
    """Match payroll/commissions: admin_user link first, then mobile fallback."""
    staff = (
        StaffProfile.objects.select_related("branch")
        .filter(admin_user=user, is_deleted=False)
        .first()
    )
    if staff:
        return staff
    mobile = (getattr(user, "mobile", "") or "").strip()
    mobile10 = mobile[-10:] if mobile.startswith("+91") else mobile
    return (
        StaffProfile.objects.select_related("branch")
        .filter(mobile=mobile10, is_deleted=False)
        .first()
    )


def build_summary_payload(staff: StaffProfile) -> dict:
    today = timezone.localdate()
    month_start = _month_floor(today)
    next_month = _add_months(month_start, 1)
    prev_month_start = _add_months(month_start, -1)

    my_profiles_total = CustomerStaffAssignment.objects.filter(staff=staff).count()
    curr_assignments = CustomerStaffAssignment.objects.filter(
        staff=staff,
        created_at__date__gte=month_start,
        created_at__date__lt=next_month,
    ).count()
    prev_assignments = CustomerStaffAssignment.objects.filter(
        staff=staff,
        created_at__date__gte=prev_month_start,
        created_at__date__lt=month_start,
    ).count()
    profiles_growth = curr_assignments - prev_assignments

    curr_txns = Transaction.objects.filter(
        payment_status=Transaction.STATUS_SUCCESS,
        transaction_type=Transaction.TYPE_PLAN_PURCHASE,
        user__staff_assignment__staff=staff,
        created_at__date__gte=month_start,
        created_at__date__lt=next_month,
    )
    prev_txns = Transaction.objects.filter(
        payment_status=Transaction.STATUS_SUCCESS,
        transaction_type=Transaction.TYPE_PLAN_PURCHASE,
        user__staff_assignment__staff=staff,
        created_at__date__gte=prev_month_start,
        created_at__date__lt=month_start,
    )
    subscriptions_this_month = curr_txns.count()
    subscriptions_prev_month = prev_txns.count()
    subscriptions_growth = subscriptions_this_month - subscriptions_prev_month

    comm_curr = (
        Commission.objects.filter(
            staff=staff,
            status__in=[Commission.STATUS_APPROVED, Commission.STATUS_PAID],
            created_at__date__gte=month_start,
            created_at__date__lt=next_month,
        ).aggregate(v=Coalesce(Sum("commission_amt"), Decimal("0")))["v"]
        or Decimal("0")
    )
    comm_prev = (
        Commission.objects.filter(
            staff=staff,
            status__in=[Commission.STATUS_APPROVED, Commission.STATUS_PAID],
            created_at__date__gte=prev_month_start,
            created_at__date__lt=month_start,
        ).aggregate(v=Coalesce(Sum("commission_amt"), Decimal("0")))["v"]
        or Decimal("0")
    )
    commission_pct = _growth_percent(comm_curr, comm_prev)
    rounded = int(round(commission_pct))
    sign = "+" if rounded >= 0 else ""
    commission_growth_pct = f"{sign}{rounded}%"

    def _signed_count_label(n: int) -> str:
        if n >= 0:
            return f"+{n}"
        return str(n)

    branch_name = ""
    if staff.branch_id:
        branch_name = staff.branch.name or ""

    return {
        "staff_name": staff.name or "",
        "branch": branch_name,
        "my_profiles": {
            "count": my_profiles_total,
            "growth": profiles_growth,
            "growth_pct": _signed_count_label(profiles_growth),
        },
        "subscriptions_this_month": {
            "count": subscriptions_this_month,
            "growth": subscriptions_growth,
            "growth_pct": _signed_count_label(subscriptions_growth),
        },
        "commission_earned": {
            "amount": int(comm_curr),
            "growth_pct": commission_growth_pct,
        },
    }
