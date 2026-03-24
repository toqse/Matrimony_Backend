import csv
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.staff_mgmt.models import StaffProfile
from master.models import Branch as MasterBranch
from plans.models import Transaction

from .serializers import SubscriptionLedgerSerializer


VALID_STATUS = {"active", "expired", "cancelled"}
VALID_PAYMENT_MODES = {"cash", "upi", "card", "netbanking"}


def _manager_branch_code(user):
    return (
        MasterBranch.objects.filter(pk=getattr(user, "branch_id", None))
        .values_list("code", flat=True)
        .first()
    )


def _base_queryset():
    return (
        Transaction.objects.filter(transaction_type=Transaction.TYPE_PLAN_PURCHASE)
        .select_related("user", "user__branch", "user__user_plan", "plan", "user__staff_assignment", "user__staff_assignment__staff")
        .order_by("-created_at")
    )


def _staff_profile_for_admin_user(user):
    e164_mobile = (getattr(user, "mobile", "") or "").strip()
    mobile10 = e164_mobile[-10:] if e164_mobile.startswith("+91") else e164_mobile
    return StaffProfile.objects.filter(mobile=mobile10, is_deleted=False).first()


def _apply_filters(qs, request, enforce_branch_scope=False, enforce_staff_scope=False):
    today = timezone.localdate()
    user = request.user

    search = (request.query_params.get("search") or "").strip()
    if search:
        qs = qs.filter(Q(user__name__icontains=search) | Q(user__matri_id__icontains=search))

    status_filter = (request.query_params.get("status") or "").strip().lower()
    if status_filter:
        if status_filter not in VALID_STATUS:
            return None, Response(
                {"success": False, "error": {"code": 400, "message": "Invalid status filter"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if status_filter == "active":
            qs = qs.filter(
                payment_status=Transaction.STATUS_SUCCESS,
                user__user_plan__is_active=True,
                user__user_plan__valid_until__gte=today,
            )
        elif status_filter == "expired":
            qs = qs.filter(payment_status=Transaction.STATUS_SUCCESS).filter(
                Q(user__user_plan__is_active=False) | Q(user__user_plan__valid_until__lt=today)
            )
        elif status_filter == "cancelled":
            qs = qs.filter(payment_status__in=[Transaction.STATUS_FAILED, Transaction.STATUS_REFUNDED])

    payment_mode = (request.query_params.get("payment_mode") or "").strip().lower()
    if payment_mode:
        if payment_mode not in VALID_PAYMENT_MODES:
            return None, Response(
                {"success": False, "error": {"code": 400, "message": "Invalid payment mode"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if payment_mode == "upi":
            qs = qs.filter(payment_method=Transaction.PAYMENT_UPI)
        elif payment_mode == "cash":
            qs = qs.filter(payment_method=Transaction.PAYMENT_MANUAL).exclude(transaction_id__icontains="netbank")
        elif payment_mode == "card":
            qs = qs.filter(payment_method__in=[Transaction.PAYMENT_RAZORPAY, Transaction.PAYMENT_STRIPE]).exclude(
                transaction_id__icontains="netbank"
            )
        elif payment_mode == "netbanking":
            qs = qs.filter(
                Q(transaction_id__icontains="netbank")
                | Q(payment_method__in=[Transaction.PAYMENT_RAZORPAY, Transaction.PAYMENT_STRIPE], transaction_id__icontains="bank")
            )

    if enforce_branch_scope or getattr(user, "role", None) == AdminUser.ROLE_BRANCH_MANAGER:
        manager_code = _manager_branch_code(user)
        qs = qs.filter(user__branch__code=manager_code) if manager_code else qs.none()

    branch_id = request.query_params.get("branch_id")
    if branch_id:
        if getattr(user, "role", None) == AdminUser.ROLE_BRANCH_MANAGER:
            manager_code = _manager_branch_code(user)
            requested_code = (
                MasterBranch.objects.filter(pk=branch_id).values_list("code", flat=True).first()
            )
            if requested_code and requested_code != manager_code:
                return None, Response(
                    {"success": False, "error": {"code": 403, "message": "Access denied"}},
                    status=status.HTTP_403_FORBIDDEN,
                )
        qs = qs.filter(user__branch_id=branch_id)

    staff_id = request.query_params.get("staff_id")
    if staff_id:
        qs = qs.filter(user__staff_assignment__staff_id=staff_id)

    if enforce_staff_scope or getattr(user, "role", None) == AdminUser.ROLE_STAFF:
        staff_profile = _staff_profile_for_admin_user(user)
        qs = qs.filter(user__staff_assignment__staff=staff_profile) if staff_profile else qs.none()

    return qs, None


class _BaseSubscriptionListView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]
    enforce_branch_scope = False
    enforce_staff_scope = False

    def get(self, request):
        qs, err = _apply_filters(
            _base_queryset(),
            request,
            enforce_branch_scope=self.enforce_branch_scope,
            enforce_staff_scope=self.enforce_staff_scope,
        )
        if err:
            return err
        page = self.paginate_queryset(qs)
        ser = SubscriptionLedgerSerializer(page if page is not None else qs, many=True)
        if page is not None:
            paged = self.get_paginated_response(ser.data).data
            return Response({"success": True, "data": paged})
        return Response({"success": True, "data": {"count": len(ser.data), "results": ser.data}})

    # lightweight pagination helpers from DRF GenericAPIView behavior
    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            from rest_framework.settings import api_settings
            pagination_class = api_settings.DEFAULT_PAGINATION_CLASS
            self._paginator = pagination_class() if pagination_class else None
        return self._paginator

    def paginate_queryset(self, queryset):
        if self.paginator is None:
            return None
        return self.paginator.paginate_queryset(queryset, self.request, view=self)

    def get_paginated_response(self, data):
        return self.paginator.get_paginated_response(data)


class AdminSubscriptionsListAPIView(_BaseSubscriptionListView):
    pass


class BranchSubscriptionsListAPIView(_BaseSubscriptionListView):
    enforce_branch_scope = True


class StaffSubscriptionsListAPIView(_BaseSubscriptionListView):
    enforce_staff_scope = True


class SubscriptionDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        qs, err = _apply_filters(_base_queryset(), request)
        if err:
            return err
        obj = qs.filter(pk=pk).first()
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Subscription not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"success": True, "data": SubscriptionLedgerSerializer(obj).data})


class SubscriptionsExportCSVAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        role = getattr(request.user, "role", None)
        if role not in {AdminUser.ROLE_ADMIN, AdminUser.ROLE_BRANCH_MANAGER}:
            return Response(
                {"success": False, "error": {"code": 403, "message": "Access denied"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        qs, err = _apply_filters(
            _base_queryset(),
            request,
            enforce_branch_scope=(role == AdminUser.ROLE_BRANCH_MANAGER),
        )
        if err:
            return err
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="subscriptions_export.csv"'
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
        # Stream rows — avoids loading entire queryset into memory (large exports).
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
