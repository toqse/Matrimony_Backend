from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_admin_role
from admin_panel.commissions.models import Commission
from admin_panel.enquiries.models import Enquiry
from admin_panel.enquiries.scoping import admin_branch_for_manager
from core.permissions import IsStaffOrAdmin
from master.models import Branch
from notifications.models import NotificationLog
from admin_panel.subscriptions.models import CustomerStaffAssignment
from plans.models import Transaction, UserPlan


def _month_floor(d: date) -> date:
    return date(d.year, d.month, 1)


def _add_months(d: date, months: int) -> date:
    # d is expected to be first-of-month.
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, 1)


def _last_12_months_inclusive(today: date) -> list[date]:
    end = _month_floor(today)
    start = _add_months(end, -11)
    return [_add_months(start, i) for i in range(12)]


def _active_subscription_qs(today: date):
    return UserPlan.objects.filter(is_active=True).filter(valid_until__gte=today)


def _staff_profile_or_none(admin_user: AdminUser):
    return getattr(admin_user, "staff_profile", None)


def _growth_percent(current: Decimal, previous: Decimal) -> float:
    if previous <= 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100.0, 1)


class SummaryView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        role = normalize_admin_role(getattr(request.user, "role", ""))
        if role == AdminUser.ROLE_STAFF:
            staff_profile = _staff_profile_or_none(request.user)
            if not staff_profile:
                return Response(
                    {"success": False, "error": {"code": 400, "message": "Staff profile not found."}},
                    status=400,
                )
            today = timezone.localdate()
            month_start = _month_floor(today)
            next_month = _add_months(month_start, 1)
            prev_month_start = _add_months(month_start, -1)

            my_profiles = CustomerStaffAssignment.objects.filter(staff=staff_profile).count()
            curr_profiles = CustomerStaffAssignment.objects.filter(
                staff=staff_profile,
                created_at__date__gte=month_start,
                created_at__date__lt=next_month,
            ).count()
            prev_profiles = CustomerStaffAssignment.objects.filter(
                staff=staff_profile,
                created_at__date__gte=prev_month_start,
                created_at__date__lt=month_start,
            ).count()

            curr_txns = Transaction.objects.filter(
                payment_status=Transaction.STATUS_SUCCESS,
                transaction_type=Transaction.TYPE_PLAN_PURCHASE,
                user__staff_assignment__staff=staff_profile,
                created_at__date__gte=month_start,
                created_at__date__lt=next_month,
            )
            prev_txns = Transaction.objects.filter(
                payment_status=Transaction.STATUS_SUCCESS,
                transaction_type=Transaction.TYPE_PLAN_PURCHASE,
                user__staff_assignment__staff=staff_profile,
                created_at__date__gte=prev_month_start,
                created_at__date__lt=month_start,
            )

            subscriptions_this_month = curr_txns.count()
            subscriptions_prev_month = prev_txns.count()
            revenue_this_month = curr_txns.aggregate(v=Coalesce(Sum("total_amount"), Decimal("0")))["v"] or Decimal("0")
            revenue_prev_month = prev_txns.aggregate(v=Coalesce(Sum("total_amount"), Decimal("0")))["v"] or Decimal("0")

            comm_curr = (
                Commission.objects.filter(
                    staff=staff_profile,
                    status__in=[Commission.STATUS_APPROVED, Commission.STATUS_PAID],
                    created_at__date__gte=month_start,
                    created_at__date__lt=next_month,
                ).aggregate(v=Coalesce(Sum("commission_amt"), Decimal("0")))["v"]
                or Decimal("0")
            )
            comm_prev = (
                Commission.objects.filter(
                    staff=staff_profile,
                    status__in=[Commission.STATUS_APPROVED, Commission.STATUS_PAID],
                    created_at__date__gte=prev_month_start,
                    created_at__date__lt=month_start,
                ).aggregate(v=Coalesce(Sum("commission_amt"), Decimal("0")))["v"]
                or Decimal("0")
            )

            return Response(
                {
                    "success": True,
                    "data": {
                        "my_profiles": my_profiles,
                        "subscriptions_this_month": subscriptions_this_month,
                        "revenue_this_month": float(revenue_this_month),
                        "commission_earned": float(comm_curr),
                        "growth": {
                            "profiles": curr_profiles - prev_profiles,
                            "subscriptions": subscriptions_this_month - subscriptions_prev_month,
                            "revenue": _growth_percent(revenue_this_month, revenue_prev_month),
                            "commission": _growth_percent(comm_curr, comm_prev),
                        },
                    },
                }
            )

        today = timezone.localdate()
        month_start = _month_floor(today)
        next_month = _add_months(month_start, 1)

        total_users = User.objects.count()
        todays_registrations = User.objects.filter(created_at__date=today).count()
        active_profiles = User.objects.filter(is_registration_profile_completed=True).count()

        total_subscriptions = _active_subscription_qs(today).count()

        # MRR: treat as "current month plan revenue" (sum of successful plan_purchase total_amount)
        mrr = (
            Transaction.objects.filter(
                payment_status=Transaction.STATUS_SUCCESS,
                transaction_type=Transaction.TYPE_PLAN_PURCHASE,
                created_at__date__gte=month_start,
                created_at__date__lt=next_month,
            ).aggregate(v=Coalesce(Sum("total_amount"), Decimal("0")))["v"]
            or Decimal("0")
        )
        total_revenue = (
            Transaction.objects.filter(payment_status=Transaction.STATUS_SUCCESS).aggregate(
                v=Coalesce(Sum("total_amount"), Decimal("0"))
            )["v"]
            or Decimal("0")
        )

        return Response(
            {
                "success": True,
                "data": {
                    "total_users": total_users,
                    "total_subscriptions": total_subscriptions,
                    "mrr": float(mrr),
                    "active_profiles": active_profiles,
                    "todays_registrations": todays_registrations,
                    "total_revenue": float(total_revenue),
                },
            }
        )


class MonthlyRevenueView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        role = normalize_admin_role(getattr(request.user, "role", ""))
        if role == AdminUser.ROLE_STAFF:
            staff_profile = _staff_profile_or_none(request.user)
            if not staff_profile:
                return Response(
                    {"success": False, "error": {"code": 400, "message": "Staff profile not found."}},
                    status=400,
                )
            today = timezone.localdate()
            months = _last_12_months_inclusive(today)
            start = months[0]
            end_exclusive = _add_months(months[-1], 1)

            rows = (
                Commission.objects.filter(
                    staff=staff_profile,
                    status__in=[Commission.STATUS_APPROVED, Commission.STATUS_PAID],
                    created_at__date__gte=start,
                    created_at__date__lt=end_exclusive,
                )
                .annotate(month=TruncMonth("created_at"))
                .values("month")
                .annotate(total=Coalesce(Sum("commission_amt"), Decimal("0")))
                .order_by("month")
            )
            by_key = {
                (r["month"].date() if hasattr(r["month"], "date") else r["month"]): r["total"] or Decimal("0")
                for r in rows
            }

            series = []
            for m in months:
                series.append({"month": m.strftime("%b %Y"), "value": float(by_key.get(m, Decimal("0")))})
            return Response({"success": True, "data": series})

        today = timezone.localdate()
        months = _last_12_months_inclusive(today)
        start = months[0]
        end_exclusive = _add_months(months[-1], 1)

        rows = (
            Transaction.objects.filter(payment_status=Transaction.STATUS_SUCCESS)
            .filter(created_at__date__gte=start, created_at__date__lt=end_exclusive)
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(total=Coalesce(Sum("total_amount"), Decimal("0")))
            .order_by("month")
        )
        by_key = {
            (r["month"].date() if hasattr(r["month"], "date") else r["month"]): r["total"] or Decimal("0")
            for r in rows
        }

        series = []
        for m in months:
            series.append({"month": m.strftime("%Y-%m"), "total_revenue": float(by_key.get(m, Decimal("0")))})

        return Response({"success": True, "data": {"series": series}})


class SubscriptionGrowthView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        today = timezone.localdate()
        months = _last_12_months_inclusive(today)
        start = months[0]
        end_exclusive = _add_months(months[-1], 1)

        rows = (
            Transaction.objects.filter(
                payment_status=Transaction.STATUS_SUCCESS,
                transaction_type=Transaction.TYPE_PLAN_PURCHASE,
            )
            .filter(created_at__date__gte=start, created_at__date__lt=end_exclusive)
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        by_key = {
            (r["month"].date() if hasattr(r["month"], "date") else r["month"]): int(r["count"] or 0)
            for r in rows
        }

        series = []
        for m in months:
            series.append({"month": m.strftime("%Y-%m"), "subscriptions": by_key.get(m, 0)})

        return Response({"success": True, "data": {"series": series}})


class BranchPerformanceView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        today = timezone.localdate()

        # Users per branch
        users = (
            User.objects.values("branch_id")
            .annotate(total_users=Count("id"))
            .order_by()
        )
        # Django <5 doesn't support Count(filter=None) for conditional; do separate query for today:
        today_users = User.objects.filter(created_at__date=today).values("branch_id").annotate(c=Count("id"))
        today_by_branch = {r["branch_id"]: int(r["c"]) for r in today_users}

        users_by_branch = {r["branch_id"]: int(r["total_users"]) for r in users}

        # Active subscriptions per branch
        active_subs = (
            _active_subscription_qs(today)
            .values("user__branch_id")
            .annotate(c=Count("id"))
            .order_by()
        )
        subs_by_branch = {r["user__branch_id"]: int(r["c"]) for r in active_subs}

        # Revenue per branch (all-time, successful)
        revenue_rows = (
            Transaction.objects.filter(payment_status=Transaction.STATUS_SUCCESS)
            .values("user__branch_id")
            .annotate(total=Coalesce(Sum("total_amount"), Decimal("0")))
            .order_by()
        )
        revenue_by_branch = {r["user__branch_id"]: r["total"] or Decimal("0") for r in revenue_rows}

        branches = list(Branch.objects.all().values("id", "name", "code"))
        known_branch_ids = {b["id"] for b in branches}

        def build_row(branch_id, name, code):
            return {
                "branch": {"id": branch_id, "name": name, "code": code},
                "total_users": users_by_branch.get(branch_id, 0),
                "active_subscriptions": subs_by_branch.get(branch_id, 0),
                "todays_registrations": today_by_branch.get(branch_id, 0),
                "total_revenue": float(revenue_by_branch.get(branch_id, Decimal("0"))),
            }

        data = [build_row(b["id"], b["name"], b["code"]) for b in branches]

        # Include unassigned (null branch) if present.
        null_present = (
            (None in users_by_branch)
            or (None in subs_by_branch)
            or (None in revenue_by_branch)
            or (None in today_by_branch)
        )
        if null_present:
            data.append(build_row(None, "Unassigned", None))

        # If any stray branch_id exists (deleted branch), include as "Unknown"
        stray_ids = (set(users_by_branch) | set(subs_by_branch) | set(revenue_by_branch) | set(today_by_branch)) - (
            known_branch_ids | {None}
        )
        for bid in sorted([x for x in stray_ids if x is not None]):
            data.append(build_row(bid, "Unknown", None))

        # Default sort by total_revenue desc
        data.sort(key=lambda r: r["total_revenue"], reverse=True)

        return Response({"success": True, "data": {"branches": data}})


class RecentActivityView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        role = normalize_admin_role(getattr(request.user, "role", ""))
        if role == AdminUser.ROLE_STAFF:
            staff_profile = _staff_profile_or_none(request.user)
            if not staff_profile:
                return Response(
                    {"success": False, "error": {"code": 400, "message": "Staff profile not found."}},
                    status=400,
                )
            logs = (
                NotificationLog.objects.filter(
                    is_deleted=False,
                    user__staff_assignment__staff=staff_profile,
                )
                .order_by("-sent_at")
                .values("id", "channel", "recipient", "success", "sent_at")[:10]
            )
            results = []
            for l in logs:
                sent_at = l["sent_at"]
                results.append(
                    {
                        "id": l["id"],
                        "type": "notification",
                        "channel": l["channel"],
                        "recipient": l["recipient"],
                        "success": bool(l["success"]),
                        "created_at": sent_at.strftime("%d-%m-%Y") if sent_at else "",
                    }
                )
            return Response({"success": True, "data": {"logs": results}})

        logs = (
            NotificationLog.objects.filter(is_deleted=False)
            .order_by("-sent_at")
            .values("id", "channel", "recipient", "subject", "success", "error_message", "sent_at")[:10]
        )
        results = []
        for l in logs:
            results.append(
                {
                    "id": l["id"],
                    "type": "notification",
                    "channel": l["channel"],
                    "recipient": l["recipient"],
                    "subject": l["subject"],
                    "success": bool(l["success"]),
                    "error_message": l["error_message"],
                    "created_at": l["sent_at"],
                }
            )
        return Response({"success": True, "data": {"logs": results}})


class LeadSourcesView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def get(self, request):
        role = normalize_admin_role(getattr(request.user, "role", ""))
        qs = Enquiry.objects.all()

        if role == AdminUser.ROLE_STAFF:
            qs = qs.filter(assigned_to=request.user)
        elif role == AdminUser.ROLE_BRANCH_MANAGER:
            branch = admin_branch_for_manager(request.user)
            if not branch:
                return Response(
                    {"success": False, "error": {"code": 400, "message": "No branch assigned to your account."}},
                    status=400,
                )
            qs = qs.filter(branch=branch)

        source_labels = dict(Enquiry.SOURCE_CHOICES)
        counts = {
            row["source"]: int(row["c"])
            for row in qs.values("source").annotate(c=Count("id"))
        }
        total = sum(counts.values())

        data = []
        for key, label in Enquiry.SOURCE_CHOICES:
            count = counts.get(key, 0)
            pct = round((count / total) * 100.0, 1) if total > 0 else 0.0
            data.append(
                {
                    "source": key,
                    "label": source_labels.get(key, label),
                    "count": count,
                    "percentage": pct,
                }
            )
        return Response({"success": True, "data": data})

