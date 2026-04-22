from __future__ import annotations

import csv

from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.pagination import StandardPagination
from admin_panel.staff_dashboard.services import resolve_staff_dashboard_request
from admin_panel.subscriptions.serializers import SubscriptionLedgerSerializer
from plans.models import Plan, Transaction

from .serializers import StaffSubscriptionCreateSerializer, StaffSubscriptionRenewSerializer
from .services import (
    apply_staff_subscription_filters,
    build_staff_subscription_summary,
    ensure_staff_owns_customer,
    export_apply_filters,
    first_serializer_error,
    record_staff_plan_purchase,
    renew_staff_plan,
    staff_subscription_same_plan_active_preflight,
    staff_subscription_transactions,
)


class _StaffSubscriptionsMixin:
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        u = getattr(request, "user", None)
        if u is not None and getattr(u, "is_authenticated", False):
            request.admin_user = u


class StaffSubscriptionSummaryView(_StaffSubscriptionsMixin, APIView):
    def get(self, request):
        staff, err = resolve_staff_dashboard_request(request)
        if err:
            return err
        data = build_staff_subscription_summary(staff)
        return Response({"success": True, "data": data})


class StaffSubscriptionListCreateView(_StaffSubscriptionsMixin, APIView):
    def get(self, request):
        staff, err = resolve_staff_dashboard_request(request)
        if err:
            return err
        qs = staff_subscription_transactions(staff)
        qs, ferr = apply_staff_subscription_filters(qs, request)
        if ferr:
            return ferr

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        ser = SubscriptionLedgerSerializer(page, many=True)
        paged = paginator.get_paginated_response(ser.data)
        return Response(
            {
                "success": True,
                "data": {
                    "count": paged.data["count"],
                    "next": paged.data.get("next"),
                    "previous": paged.data.get("previous"),
                    "results": paged.data["results"],
                },
            }
        )

    def post(self, request):
        staff, err = resolve_staff_dashboard_request(request)
        if err:
            return err

        ser = StaffSubscriptionCreateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": first_serializer_error(ser)},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        mid = (ser.validated_data.get("customer_matri_id") or "").strip()
        customer = (
            User.objects.filter(matri_id__iexact=mid, role="user", is_active=True).first()
            if mid
            else None
        )
        if not customer:
            return Response(
                {
                    "success": False,
                    "error": {"code": 404, "message": "Customer not found."},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        plan_id = ser.validated_data["plan_id"]
        plan = Plan.objects.filter(pk=plan_id, is_active=True).first()
        if not plan:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Invalid or inactive plan."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        blocked_msg = staff_subscription_same_plan_active_preflight(customer, plan)
        if blocked_msg:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "ACTIVE_SAME_PLAN",
                        "message": blocked_msg,
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )

        own_err = ensure_staff_owns_customer(staff, customer)
        if own_err is not None:
            return own_err

        try:
            txn = record_staff_plan_purchase(
                customer=customer,
                plan=plan,
                payment_mode=ser.validated_data["payment_mode"],
                payment_reference=ser.validated_data.get("payment_reference") or "",
                amount=ser.validated_data["amount"],
            )
        except ValueError as e:
            msg = str(e)
            if "already has an active" in msg and "Use renew instead" in msg:
                return Response(
                    {
                        "success": False,
                        "error": {"code": "ACTIVE_SAME_PLAN", "message": msg},
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": msg},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        txn = (
            Transaction.objects.select_related(
                "user",
                "user__branch",
                "user__user_plan",
                "plan",
                "user__staff_assignment",
                "user__staff_assignment__staff",
            )
            .filter(pk=txn.pk)
            .first()
        )
        return Response(
            {
                "success": True,
                "message": "Subscription recorded successfully.",
                "data": SubscriptionLedgerSerializer(txn).data,
            },
            status=status.HTTP_201_CREATED,
        )


class StaffSubscriptionDetailView(_StaffSubscriptionsMixin, APIView):
    def get(self, request, pk):
        staff, err = resolve_staff_dashboard_request(request)
        if err:
            return err
        qs = staff_subscription_transactions(staff)
        obj = qs.filter(pk=pk).first()
        if not obj:
            return Response(
                {
                    "success": False,
                    "error": {"code": 404, "message": "Subscription not found."},
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"success": True, "data": SubscriptionLedgerSerializer(obj).data})

    def delete(self, request, pk):
        staff, err = resolve_staff_dashboard_request(request)
        if err:
            return err
        _ = pk
        return Response(
            {
                "success": False,
                "error": {
                    "code": 403,
                    "message": "Subscription deletion requires Admin role.",
                },
            },
            status=status.HTTP_403_FORBIDDEN,
        )


class StaffSubscriptionRenewView(_StaffSubscriptionsMixin, APIView):
    def post(self, request, pk):
        staff, err = resolve_staff_dashboard_request(request)
        if err:
            return err

        ser = StaffSubscriptionRenewSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": first_serializer_error(ser)},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = staff_subscription_transactions(staff)
        ledger_txn = qs.filter(pk=pk).first()
        if not ledger_txn:
            return Response(
                {
                    "success": False,
                    "error": {"code": 404, "message": "Subscription not found."},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        own_err = ensure_staff_owns_customer(staff, ledger_txn.user)
        if own_err is not None:
            return own_err

        try:
            txn = renew_staff_plan(
                ledger_txn=ledger_txn,
                payment_mode=ser.validated_data["payment_mode"],
                payment_reference=ser.validated_data.get("payment_reference") or "",
                amount=ser.validated_data["amount"],
            )
        except ValueError as e:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": str(e)},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        txn = (
            Transaction.objects.select_related(
                "user",
                "user__branch",
                "user__user_plan",
                "plan",
                "user__staff_assignment",
                "user__staff_assignment__staff",
            )
            .filter(pk=txn.pk)
            .first()
        )
        return Response(
            {
                "success": True,
                "message": "Subscription renewed successfully.",
                "data": SubscriptionLedgerSerializer(txn).data,
            },
            status=status.HTTP_201_CREATED,
        )


class StaffSubscriptionExportView(_StaffSubscriptionsMixin, APIView):
    def get(self, request):
        staff, err = resolve_staff_dashboard_request(request)
        if err:
            return err

        qs = staff_subscription_transactions(staff)
        qs, eerr = export_apply_filters(qs, request)
        if eerr:
            return eerr

        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="staff_subscriptions_export.csv"'
        writer = csv.writer(resp)
        writer.writerow(
            [
                "Customer",
                "Matri ID",
                "Plan",
                "Amount Paid",
                "Payment Mode",
                "Staff",
                "Branch",
                "Start Date",
                "Expiry Date",
                "Status",
            ]
        )
        for txn in qs.iterator(chunk_size=500):
            row = SubscriptionLedgerSerializer(txn).data
            writer.writerow(
                [
                    row.get("customer", ""),
                    row.get("matri_id", ""),
                    row.get("plan", ""),
                    row.get("amount", ""),
                    row.get("payment_mode", ""),
                    row.get("staff", ""),
                    row.get("branch", ""),
                    row.get("start_date", ""),
                    row.get("expiry_date", ""),
                    row.get("status", ""),
                ]
            )
        return resp
