from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.commissions.models import Commission
from admin_panel.enquiries.models import Enquiry
from admin_panel.pagination import StandardPagination
from admin_panel.permissions import IsBranchManagerOnly
from admin_panel.staff_mgmt.models import StaffProfile
from plans.models import Transaction, UserPlan

from .helpers import (
    add_months,
    admin_branch_for_request,
    branch_manager_context,
    calendar_month_bounds,
    decimal_to_float,
    last_12_months_inclusive,
    pct_change,
)


def _active_subscription_qs(today, master_branch_id: int):
    return UserPlan.objects.filter(
        is_active=True,
        valid_until__gte=today,
        user__branch_id=master_branch_id,
    )


class BranchDashboardSummaryView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManagerOnly]

    def get(self, request):
        master_bid, err = branch_manager_context(request)
        if err:
            return err
        today = timezone.localdate()
        cur_start, next_start, prev_start = calendar_month_bounds(today)

        branch_profiles = User.objects.filter(branch_id=master_bid).count()
        branch_subscriptions = _active_subscription_qs(today, master_bid).count()

        branch_revenue = (
            Transaction.objects.filter(
                payment_status=Transaction.STATUS_SUCCESS,
                user__branch_id=master_bid,
            ).aggregate(v=Coalesce(Sum("total_amount"), Decimal("0")))["v"]
            or Decimal("0")
        )

        ab = admin_branch_for_request(request)
        active_staff = 0
        if ab:
            active_staff = StaffProfile.objects.filter(
                branch=ab, is_deleted=False, is_active=True
            ).count()

        new_profiles_cur = User.objects.filter(
            branch_id=master_bid,
            created_at__date__gte=cur_start,
            created_at__date__lt=next_start,
        ).count()
        new_profiles_prev = User.objects.filter(
            branch_id=master_bid,
            created_at__date__gte=prev_start,
            created_at__date__lt=cur_start,
        ).count()

        def _txn_in_range(start_d, end_d):
            return Transaction.objects.filter(
                payment_status=Transaction.STATUS_SUCCESS,
                transaction_type=Transaction.TYPE_PLAN_PURCHASE,
                user__branch_id=master_bid,
                created_at__date__gte=start_d,
                created_at__date__lt=end_d,
            )

        subs_txn_cur = _txn_in_range(cur_start, next_start).count()
        subs_txn_prev = _txn_in_range(prev_start, cur_start).count()

        def _revenue_in_range(start_d, end_d):
            return (
                Transaction.objects.filter(
                    payment_status=Transaction.STATUS_SUCCESS,
                    user__branch_id=master_bid,
                    created_at__date__gte=start_d,
                    created_at__date__lt=end_d,
                ).aggregate(v=Coalesce(Sum("total_amount"), Decimal("0")))["v"]
                or Decimal("0")
            )

        rev_cur = _revenue_in_range(cur_start, next_start)
        rev_prev = _revenue_in_range(prev_start, cur_start)

        growth_staff = 0.0

        return Response(
            {
                "success": True,
                "data": {
                    "branch_profiles": branch_profiles,
                    "branch_subscriptions": branch_subscriptions,
                    "branch_revenue": decimal_to_float(branch_revenue),
                    "active_staff": active_staff,
                    "growth": {
                        "profiles": pct_change(float(new_profiles_cur), float(new_profiles_prev)),
                        "subscriptions": pct_change(float(subs_txn_cur), float(subs_txn_prev)),
                        "revenue": pct_change(decimal_to_float(rev_cur), decimal_to_float(rev_prev)),
                        "staff": growth_staff,
                    },
                },
            }
        )


class BranchRevenueTrendView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManagerOnly]

    def get(self, request):
        master_bid, err = branch_manager_context(request)
        if err:
            return err
        today = timezone.localdate()
        months = last_12_months_inclusive(today)
        start = months[0]
        end_exclusive = add_months(months[-1], 1)

        rows = (
            Transaction.objects.filter(
                payment_status=Transaction.STATUS_SUCCESS,
                user__branch_id=master_bid,
            )
            .filter(created_at__date__gte=start, created_at__date__lt=end_exclusive)
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(total=Coalesce(Sum("total_amount"), Decimal("0")))
            .order_by("month")
        )
        by_key = {}
        for r in rows:
            m = r["month"]
            key = m.date() if hasattr(m, "date") else m
            by_key[key] = r["total"] or Decimal("0")

        series = []
        for m in months:
            series.append(
                {"month": m.strftime("%Y-%m"), "total_revenue": float(by_key.get(m, Decimal("0")))}
            )

        return Response({"success": True, "data": {"series": series}})


class BranchStaffPerformanceView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManagerOnly]

    def get(self, request):
        master_bid, err = branch_manager_context(request)
        if err:
            return err
        ab = admin_branch_for_request(request)
        if not ab:
            return Response({"success": True, "data": {"staff": []}})

        staff_list = list(
            StaffProfile.objects.filter(branch=ab, is_deleted=False)
            .order_by("name")
            .values("id", "name")
        )
        if not staff_list:
            return Response({"success": True, "data": {"staff": []}})

        rev_rows = (
            Transaction.objects.filter(
                payment_status=Transaction.STATUS_SUCCESS,
                user__branch_id=master_bid,
                user__staff_assignment__staff__branch=ab,
            )
            .values("user__staff_assignment__staff_id")
            .annotate(revenue=Coalesce(Sum("total_amount"), Decimal("0")))
        )
        rev_by_staff = {r["user__staff_assignment__staff_id"]: r["revenue"] or Decimal("0") for r in rev_rows}

        comm_rows = (
            Commission.objects.filter(branch=ab)
            .exclude(status=Commission.STATUS_CANCELLED)
            .values("staff_id")
            .annotate(commission=Coalesce(Sum("commission_amt"), Decimal("0")))
        )
        comm_by_staff = {r["staff_id"]: r["commission"] or Decimal("0") for r in comm_rows}

        out = []
        for s in staff_list:
            sid = s["id"]
            out.append(
                {
                    "staff_id": sid,
                    "staff_name": s["name"],
                    "revenue": decimal_to_float(rev_by_staff.get(sid)),
                    "commission": decimal_to_float(comm_by_staff.get(sid)),
                }
            )

        return Response({"success": True, "data": {"staff": out}})


class BranchTargetProgressView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManagerOnly]

    def get(self, request):
        master_bid, err = branch_manager_context(request)
        if err:
            return err
        ab = admin_branch_for_request(request)
        if not ab:
            return Response({"success": True, "data": {"staff": []}})

        rows = (
            StaffProfile.objects.filter(branch=ab, is_deleted=False)
            .order_by("name")
            .values("id", "name", "monthly_target", "achieved_target")
        )
        data = [
            {
                "staff_id": r["id"],
                "staff_name": r["name"],
                "target": int(r["monthly_target"] or 0),
                "achieved": int(r["achieved_target"] or 0),
            }
            for r in rows
        ]
        return Response({"success": True, "data": {"staff": data}})


class BranchTopPerformersView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManagerOnly]

    def get(self, request):
        master_bid, err = branch_manager_context(request)
        if err:
            return err
        ab = admin_branch_for_request(request)
        if not ab:
            return Response({"success": True, "data": []})

        staff_rows = list(
            StaffProfile.objects.filter(branch=ab, is_deleted=False).values("id", "name", "monthly_target")
        )
        if not staff_rows:
            return Response({"success": True, "data": []})

        rev_rows = (
            Transaction.objects.filter(
                payment_status=Transaction.STATUS_SUCCESS,
                transaction_type=Transaction.TYPE_PLAN_PURCHASE,
                user__branch_id=master_bid,
                user__staff_assignment__staff__branch=ab,
            )
            .values("user__staff_assignment__staff_id")
            .annotate(
                revenue=Coalesce(Sum("total_amount"), Decimal("0")),
                subscriptions=Count("id"),
            )
        )
        by_staff = {r["user__staff_assignment__staff_id"]: r for r in rev_rows}

        ranked = []
        for s in staff_rows:
            sid = s["id"]
            row = by_staff.get(sid) or {}
            revenue = decimal_to_float(row.get("revenue"))
            subscriptions = int(row.get("subscriptions") or 0)
            target = int(s["monthly_target"] or 0)
            if target > 0:
                conversion_rate = round(subscriptions / target * 100.0, 1)
            else:
                conversion_rate = round(100.0 if subscriptions > 0 else 0.0, 1)
            ranked.append(
                {
                    "staff_name": s["name"],
                    "revenue": revenue,
                    "subscriptions": subscriptions,
                    "conversion_rate": conversion_rate,
                    "_sort": revenue,
                }
            )

        ranked.sort(key=lambda x: x["_sort"], reverse=True)
        badges = ["gold", "silver", "bronze"]
        data = []
        for i, item in enumerate(ranked[:3]):
            data.append(
                {
                    "rank": i + 1,
                    "staff_name": item["staff_name"],
                    "revenue": item["revenue"],
                    "subscriptions": item["subscriptions"],
                    "conversion_rate": item["conversion_rate"],
                    "badge": badges[i] if i < 3 else "bronze",
                }
            )

        return Response({"success": True, "data": data})


class BranchEnquiryOverviewView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManagerOnly]

    def get(self, request):
        master_bid, err = branch_manager_context(request)
        if err:
            return err
        ab = admin_branch_for_request(request)
        if not ab:
            return Response(
                {
                    "success": True,
                    "data": {"count": 0, "next": None, "previous": None, "results": []},
                }
            )

        qs = (
            Enquiry.objects.filter(branch=ab)
            .select_related("assigned_to")
            .order_by("-created_at")
        )

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)

        def last_contact(e: Enquiry) -> str:
            ts = e.updated_at or e.created_at
            if isinstance(ts, datetime):
                return ts.date().isoformat()
            return str(ts)[:10] if ts else ""

        results = []
        for e in page:
            results.append(
                {
                    "id": e.id,
                    "lead_name": e.name,
                    "source": e.source,
                    "status": e.status,
                    "assigned_to_name": e.assigned_to.name if e.assigned_to_id else None,
                    "last_contact": last_contact(e),
                    "can_reassign": True,
                }
            )

        return Response(
            {
                "success": True,
                "data": {
                    "count": paginator.page.paginator.count,
                    "next": paginator.get_next_link(),
                    "previous": paginator.get_previous_link(),
                    "results": results,
                },
            }
        )
