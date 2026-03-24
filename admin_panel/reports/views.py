"""
Reports & Analytics APIs — Admin (all branches) | Branch Manager (own branch only).
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce, TruncDate, TruncMonth, TruncYear
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch as AdminBranch
from admin_panel.commissions.models import Commission
from admin_panel.enquiries.scoping import manager_branch_code
from admin_panel.staff_mgmt.models import StaffProfile
from master.models import Branch as MasterBranch
from plans.models import Transaction
from profiles.models import UserProfile


class IsAdminOrBranchManagerOnly(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False
        return getattr(user, "role", None) in (
            AdminUser.ROLE_ADMIN,
            AdminUser.ROLE_BRANCH_MANAGER,
        )


def _parse_date(s: str | None, name: str):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid {name}, use YYYY-MM-DD")


def _get_date_range(request, default_days: int = 30):
    """Accept start_date/end_date or start/end aliases."""
    start_s = request.query_params.get("start_date") or request.query_params.get("start")
    end_s = request.query_params.get("end_date") or request.query_params.get("end")
    today = timezone.localdate()
    if start_s or end_s:
        start_d = _parse_date(start_s, "start_date") if start_s else None
        end_d = _parse_date(end_s, "end_date") if end_s else None
        if start_d is None and end_d is not None:
            start_d = end_d - timedelta(days=default_days - 1)
        if end_d is None and start_d is not None:
            end_d = today
        if start_d is None:
            start_d = today - timedelta(days=default_days - 1)
        if end_d is None:
            end_d = today
    else:
        end_d = today
        start_d = end_d - timedelta(days=default_days - 1)
    if start_d > end_d:
        raise ValueError("start_date must be on or before end_date")
    return start_d, end_d


def _branch_scope_master_id(request, user: AdminUser) -> int | None:
    """
    Returns master Branch.id to filter user__branch_id, or None for all branches.
    Branch managers are forced to their branch; admins may pass branch_id (master PK).
    """
    if user.role == AdminUser.ROLE_BRANCH_MANAGER:
        return getattr(user, "branch_id", None)
    raw = (request.query_params.get("branch_id") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise ValueError("branch_id must be a valid integer (master branch id)")


def _transaction_base_qs():
    return Transaction.objects.filter(
        payment_status=Transaction.STATUS_SUCCESS,
        transaction_type=Transaction.TYPE_PLAN_PURCHASE,
    ).select_related("plan", "user")


def _apply_branch_txn(qs, master_branch_id: int | None):
    if master_branch_id is not None:
        return qs.filter(user__branch_id=master_branch_id)
    return qs


def _aware_range(start_d: date, end_d: date):
    start = timezone.make_aware(datetime.combine(start_d, time.min))
    end_exclusive = timezone.make_aware(datetime.combine(end_d + timedelta(days=1), time.min))
    return start, end_exclusive


def _month_bounds(month_str: str) -> tuple[datetime, datetime]:
    month_str = (month_str or "").strip()
    if len(month_str) != 7 or month_str[4] != "-":
        raise ValueError("Invalid month, use YYYY-MM")
    y, m = int(month_str[:4]), int(month_str[5:7])
    if m < 1 or m > 12:
        raise ValueError("Invalid month, use YYYY-MM")
    start_d = date(y, m, 1)
    last = monthrange(y, m)[1]
    end_d = date(y, m, last)
    return _aware_range(start_d, end_d)


def _staff_queryset(user: AdminUser, master_branch_id: int | None):
    qs = StaffProfile.objects.filter(is_deleted=False, is_active=True).select_related("branch")
    if user.role == AdminUser.ROLE_BRANCH_MANAGER:
        code = manager_branch_code(user)
        return qs.filter(branch__code=code) if code else qs.none()
    if master_branch_id is not None:
        mb = MasterBranch.objects.filter(pk=master_branch_id).values_list("code", flat=True).first()
        if mb:
            return qs.filter(branch__code=mb)
        return qs.filter(branch_id=master_branch_id)
    return qs


def _float_money(v) -> float:
    return float(v or 0)


class RevenueReportAPIView(APIView):
    """
    GET /api/v1/admin/reports/revenue/
    ?period=daily|monthly|yearly&start_date=&end_date=&branch_id=
    Aliases: start=, end=
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminOrBranchManagerOnly]

    def get(self, request):
        try:
            period = (request.query_params.get("period") or "monthly").strip().lower()
            if period not in {"daily", "monthly", "yearly"}:
                return Response(
                    {"success": False, "error": {"code": 400, "message": "period must be daily, monthly, or yearly"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if period == "daily":
                start_d, end_d = _get_date_range(request, default_days=30)
            elif period == "monthly":
                start_d, end_d = _get_date_range(request, default_days=365)
            else:
                start_d, end_d = _get_date_range(request, default_days=365 * 5)

            master_bid = _branch_scope_master_id(request, request.user)
            qs = _apply_branch_txn(_transaction_base_qs(), master_bid)
            start_dt, end_ex = _aware_range(start_d, end_d)
            qs = qs.filter(created_at__gte=start_dt, created_at__lt=end_ex)

            total = qs.aggregate(v=Coalesce(Sum("total_amount"), Decimal("0")))["v"] or Decimal("0")

            if period == "daily":
                trunc = TruncDate("created_at")
                label_fmt = "%Y-%m-%d"
            elif period == "monthly":
                trunc = TruncMonth("created_at")
                label_fmt = "%b %Y"
            else:
                trunc = TruncYear("created_at")
                label_fmt = "%Y"

            chart_rows = (
                qs.annotate(bucket=trunc)
                .values("bucket")
                .annotate(value=Coalesce(Sum("total_amount"), Decimal("0")))
                .order_by("bucket")
            )
            chart = []
            for r in chart_rows:
                b = r["bucket"]
                if hasattr(b, "strftime"):
                    label = b.strftime(label_fmt)
                else:
                    label = str(b)
                chart.append({"label": label, "value": _float_money(r["value"])})

            by_plan_rows = (
                qs.values("plan__name")
                .annotate(revenue=Coalesce(Sum("total_amount"), Decimal("0")), count=Count("id"))
                .order_by("-revenue")
            )
            by_plan = [
                {
                    "plan": (r["plan__name"] or "Unknown"),
                    "revenue": _float_money(r["revenue"]),
                    "count": r["count"],
                }
                for r in by_plan_rows
            ]

            by_branch_rows = (
                qs.values("user__branch_id", "user__branch__name")
                .annotate(revenue=Coalesce(Sum("total_amount"), Decimal("0")), count=Count("id"))
                .order_by("-revenue")
            )
            by_branch = [
                {
                    "branch": r["user__branch__name"] or ("Unassigned" if r["user__branch_id"] is None else "Unknown"),
                    "branch_id": r["user__branch_id"],
                    "revenue": _float_money(r["revenue"]),
                    "count": r["count"],
                }
                for r in by_branch_rows
            ]

            summary_table = [
                {
                    "metric": "Total revenue",
                    "value": _float_money(total),
                    "period": period,
                    "from": start_d.isoformat(),
                    "to": end_d.isoformat(),
                }
            ]

            return Response(
                {
                    "success": True,
                    "data": {
                        "total": _float_money(total),
                        "period": period,
                        "start_date": start_d.isoformat(),
                        "end_date": end_d.isoformat(),
                        "branch_id": master_bid,
                        "chart": chart,
                        "by_plan": by_plan,
                        "by_branch": by_branch,
                        "summary_table": summary_table,
                    },
                }
            )
        except ValueError as e:
            return Response(
                {"success": False, "error": {"code": 400, "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ProductivityReportAPIView(APIView):
    """
    GET /api/v1/admin/reports/productivity/
    ?month=YYYY-MM&branch_id=
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminOrBranchManagerOnly]

    def get(self, request):
        try:
            month_s = (request.query_params.get("month") or "").strip()
            if not month_s:
                t = timezone.localdate()
                month_s = f"{t.year:04d}-{t.month:02d}"
            start_dt, end_ex = _month_bounds(month_s)
            master_bid = _branch_scope_master_id(request, request.user)
            staff_qs = _staff_queryset(
                request.user,
                master_bid if request.user.role == AdminUser.ROLE_ADMIN else None,
            )

            tx_qs = _apply_branch_txn(_transaction_base_qs(), master_bid).filter(
                created_at__gte=start_dt,
                created_at__lt=end_ex,
            )
            sold_by_staff = dict(
                tx_qs.filter(user__staff_assignment__staff_id__isnull=False)
                .values("user__staff_assignment__staff_id")
                .annotate(c=Count("id"))
                .values_list("user__staff_assignment__staff_id", "c")
            )

            comm_qs = Commission.objects.filter(created_at__gte=start_dt, created_at__lt=end_ex)
            if request.user.role == AdminUser.ROLE_BRANCH_MANAGER:
                code = manager_branch_code(request.user)
                if code:
                    comm_qs = comm_qs.filter(branch__code=code)
                else:
                    comm_qs = comm_qs.none()
            elif master_bid is not None:
                mb_code = MasterBranch.objects.filter(pk=master_bid).values_list("code", flat=True).first()
                if mb_code:
                    comm_qs = comm_qs.filter(branch__code=mb_code)
                else:
                    ab = AdminBranch.objects.filter(pk=master_bid, is_deleted=False).first()
                    if ab:
                        comm_qs = comm_qs.filter(branch=ab)
                    else:
                        comm_qs = comm_qs.none()

            comm_by_staff = dict(
                comm_qs.values("staff_id")
                .annotate(v=Coalesce(Sum("commission_amt"), Decimal("0")))
                .values_list("staff_id", "v")
            )

            chart = []
            summary_table = []
            for sp in staff_qs.order_by("name"):
                sold = int(sold_by_staff.get(sp.id, 0))
                earned = comm_by_staff.get(sp.id) or Decimal("0")
                target = int(sp.monthly_target or 0)
                achieved = int(sp.achieved_target or 0)
                target_met = achieved >= target if target > 0 else None
                chart.append(
                    {
                        "label": sp.name,
                        "value": _float_money(earned),
                        "subscriptions_sold": sold,
                    }
                )
                summary_table.append(
                    {
                        "staff_id": sp.id,
                        "staff_name": sp.name,
                        "emp_code": sp.emp_code,
                        "branch": sp.branch.name if sp.branch_id else None,
                        "subscriptions_sold": sold,
                        "commission_earned": _float_money(earned),
                        "monthly_target": target,
                        "achieved_target": achieved,
                        "target_met": target_met,
                        "target_progress_pct": round((achieved / target) * 100, 2) if target else None,
                    }
                )

            return Response(
                {
                    "success": True,
                    "data": {
                        "month": month_s,
                        "branch_id": master_bid,
                        "chart": chart,
                        "summary_table": summary_table,
                    },
                }
            )
        except ValueError as e:
            return Response(
                {"success": False, "error": {"code": 400, "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )


def _month_floor(d: date) -> date:
    return date(d.year, d.month, 1)


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, 1)


class GrowthReportAPIView(APIView):
    """
    GET /api/v1/admin/reports/growth/
    ?period=monthly&months=12&start_date=&end_date=&branch_id=
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminOrBranchManagerOnly]

    def get(self, request):
        try:
            period = (request.query_params.get("period") or "monthly").strip().lower()
            if period != "monthly":
                return Response(
                    {"success": False, "error": {"code": 400, "message": "Only period=monthly is supported for growth"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            months_n = int(request.query_params.get("months") or 12)
            if months_n < 1 or months_n > 60:
                return Response(
                    {"success": False, "error": {"code": 400, "message": "months must be between 1 and 60"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            today = timezone.localdate()
            if request.query_params.get("start_date") or request.query_params.get("start") or request.query_params.get("end_date") or request.query_params.get("end"):
                start_d, end_d = _get_date_range(request, default_days=365)
                start_m = _month_floor(start_d)
                end_m = _month_floor(end_d)
            else:
                end_m = _month_floor(today)
                start_m = _add_months(end_m, -(months_n - 1))

            month_list = []
            cur = start_m
            while cur <= end_m:
                month_list.append(cur)
                cur = _add_months(cur, 1)

            master_bid = _branch_scope_master_id(request, request.user)
            start_dt = timezone.make_aware(datetime.combine(start_m, time.min))
            last_day = monthrange(end_m.year, end_m.month)[1]
            end_ex = timezone.make_aware(
                datetime.combine(date(end_m.year, end_m.month, last_day) + timedelta(days=1), time.min)
            )

            user_qs = User.objects.filter(role="user", created_at__gte=start_dt, created_at__lt=end_ex)
            txn_qs = _apply_branch_txn(_transaction_base_qs(), master_bid).filter(
                created_at__gte=start_dt,
                created_at__lt=end_ex,
            )
            if master_bid is not None:
                user_qs = user_qs.filter(branch_id=master_bid)

            def _bucket_to_month_first(b):
                if b is None:
                    return None
                if hasattr(b, "date"):
                    b = b.date()
                return date(b.year, b.month, 1)

            reg_rows = (
                user_qs.annotate(bucket=TruncMonth("created_at"))
                .values("bucket")
                .annotate(count=Count("id"))
                .order_by("bucket")
            )
            reg_map = {}
            for r in reg_rows:
                key = _bucket_to_month_first(r["bucket"])
                if key:
                    reg_map[key] = r["count"]

            sub_rows = (
                txn_qs.annotate(bucket=TruncMonth("created_at"))
                .values("bucket")
                .annotate(count=Count("id"))
                .order_by("bucket")
            )
            sub_map = {}
            for r in sub_rows:
                key = _bucket_to_month_first(r["bucket"])
                if key:
                    sub_map[key] = r["count"]

            chart = []
            summary_table = []
            total_reg = 0
            total_sub = 0
            for m in month_list:
                label = m.strftime("%b %Y")
                rc = int(reg_map.get(m, 0))
                sc = int(sub_map.get(m, 0))
                total_reg += rc
                total_sub += sc
                chart.append(
                    {
                        "label": label,
                        "new_registrations": rc,
                        "new_subscriptions": sc,
                    }
                )
                summary_table.append(
                    {
                        "month": m.strftime("%Y-%m"),
                        "new_registrations": rc,
                        "new_subscriptions": sc,
                    }
                )

            return Response(
                {
                    "success": True,
                    "data": {
                        "period": "monthly",
                        "branch_id": master_bid,
                        "chart": chart,
                        "summary_table": summary_table,
                        "totals": {"new_registrations": total_reg, "new_subscriptions": total_sub},
                    },
                }
            )
        except ValueError as e:
            return Response(
                {"success": False, "error": {"code": 400, "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )


PROFILE_STEPS = (
    ("location", "location_completed", "Location"),
    ("religion", "religion_completed", "Religion & caste"),
    ("personal", "personal_completed", "Personal details"),
    ("family", "family_completed", "Family"),
    ("education", "education_completed", "Education & career"),
    ("about", "about_completed", "About me"),
    ("photos", "photos_completed", "Photos"),
)


class ProfileCompletionReportAPIView(APIView):
    """
    GET /api/v1/admin/reports/profile-completion/
    ?branch_id=
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminOrBranchManagerOnly]

    def get(self, request):
        try:
            master_bid = _branch_scope_master_id(request, request.user)
            base = UserProfile.objects.select_related("user").filter(user__role="user")
            if master_bid is not None:
                base = base.filter(user__branch_id=master_bid)

            total_profiles = base.count()
            chart = []
            summary_table = []
            for key, field, title in PROFILE_STEPS:
                incomplete = base.filter(**{field: False}).count()
                complete = total_profiles - incomplete
                pct = round((incomplete / total_profiles) * 100, 2) if total_profiles else 0.0
                chart.append({"label": title, "step": key, "incomplete_count": incomplete, "percent_of_profiles": pct})
                summary_table.append(
                    {
                        "step": key,
                        "step_label": title,
                        "incomplete_count": incomplete,
                        "complete_count": complete,
                        "percent_incomplete": pct,
                    }
                )

            fully_complete = base.filter(
                location_completed=True,
                religion_completed=True,
                personal_completed=True,
                family_completed=True,
                education_completed=True,
                about_completed=True,
                photos_completed=True,
            ).count()

            return Response(
                {
                    "success": True,
                    "data": {
                        "branch_id": master_bid,
                        "total_profiles": total_profiles,
                        "fully_complete_count": fully_complete,
                        "chart": chart,
                        "summary_table": summary_table,
                    },
                }
            )
        except ValueError as e:
            return Response(
                {"success": False, "error": {"code": 400, "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )


class PlanPopularityReportAPIView(APIView):
    """
    GET /api/v1/admin/reports/plan-popularity/
    ?start_date=&end_date=&branch_id=
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminOrBranchManagerOnly]

    def get(self, request):
        try:
            start_d, end_d = _get_date_range(request, default_days=365)
            master_bid = _branch_scope_master_id(request, request.user)
            start_dt, end_ex = _aware_range(start_d, end_d)
            qs = _apply_branch_txn(_transaction_base_qs(), master_bid).filter(
                created_at__gte=start_dt,
                created_at__lt=end_ex,
            )

            rows = (
                qs.values("plan_id", "plan__name")
                .annotate(subscriber_count=Count("id"), revenue=Coalesce(Sum("total_amount"), Decimal("0")))
                .order_by("-subscriber_count")
            )
            chart = []
            summary_table = []
            for r in rows:
                name = r["plan__name"] or "Unknown"
                chart.append({"label": name, "value": _float_money(r["revenue"]), "count": r["subscriber_count"]})
                summary_table.append(
                    {
                        "plan_id": r["plan_id"],
                        "plan": name,
                        "subscriber_count": r["subscriber_count"],
                        "revenue": _float_money(r["revenue"]),
                    }
                )

            total_rev = qs.aggregate(v=Coalesce(Sum("total_amount"), Decimal("0")))["v"] or Decimal("0")
            total_sales = qs.count()

            return Response(
                {
                    "success": True,
                    "data": {
                        "start_date": start_d.isoformat(),
                        "end_date": end_d.isoformat(),
                        "branch_id": master_bid,
                        "total_revenue": _float_money(total_rev),
                        "total_sales": total_sales,
                        "chart": chart,
                        "summary_table": summary_table,
                    },
                }
            )
        except ValueError as e:
            return Response(
                {"success": False, "error": {"code": 400, "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
