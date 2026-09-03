from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import (
    Count,
    DecimalField,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
)
from django.db.models.functions import Coalesce
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.audit_log.mixins import AuditLogMixin
from admin_panel.audit_log.models import AuditLog
from admin_panel.staff_mgmt.soft_delete import release_staff_unique_fields
from plans.models import Transaction
from .models import Branch
from .serializers import BranchSerializer, PublicBranchSerializer

User = get_user_model()


def _annotate_branch_metrics(queryset):
    """Attach per-branch revenue and profile counts.

    Customer accounts (``User.branch``) and transactions link to ``master.Branch``,
    which is correlated to the admin ``branches.Branch`` by ``code`` (see
    ``staff_mgmt.branch_sync``), so the metrics are matched on ``code``.
    """
    revenue_subquery = (
        Transaction.objects.filter(
            payment_status=Transaction.STATUS_SUCCESS,
            user__branch__code=OuterRef("code"),
        )
        .values("user__branch__code")
        .annotate(total=Sum("total_amount"))
        .values("total")[:1]
    )
    profiles_subquery = (
        User.objects.filter(branch__code=OuterRef("code"))
        .values("branch__code")
        .annotate(c=Count("id"))
        .values("c")[:1]
    )
    return queryset.annotate(
        revenue=Coalesce(
            Subquery(
                revenue_subquery,
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            Decimal("0"),
        ),
        profiles_count=Coalesce(
            Subquery(profiles_subquery, output_field=IntegerField()),
            0,
        ),
    )


def _build_summary_for_branches(branch_qs):
    branch_codes_qs = branch_qs.values("code")
    total_branches = branch_qs.count()
    total_staff = AdminUser.objects.filter(
        is_active=True,
        role__in=[AdminUser.ROLE_BRANCH_MANAGER, AdminUser.ROLE_STAFF],
        branch__code__in=branch_codes_qs,
    ).count()
    total_revenue = (
        Transaction.objects.filter(
            payment_status=Transaction.STATUS_SUCCESS,
            user__branch__code__in=branch_codes_qs,
        )
        .aggregate(v=Coalesce(Sum("total_amount"), Decimal("0")))
        .get("v")
        or Decimal("0")
    )
    return {
        "total_branches": total_branches,
        "total_staff": total_staff,
        "total_revenue": float(total_revenue),
    }


class BranchViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Branch.objects.filter(is_deleted=False)
    serializer_class = BranchSerializer
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(city__icontains=search) |
                Q(code__icontains=search)
            )

        return _annotate_branch_metrics(queryset)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        summary = _build_summary_for_branches(queryset)

        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response({
                "summary": summary,
                "results": serializer.data
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "summary": summary,
            "results": serializer.data
        })

    @action(detail=True, methods=["patch"], url_path="toggle-status")
    def toggle_status(self, request, pk=None):
        branch = self.get_object()

        prev_status = branch.is_active

        with transaction.atomic():
            branch.is_active = not branch.is_active
            branch.save(update_fields=["is_active"])

            if not branch.is_active:
                # Deactivating the branch: lock out every active staff in it and
                # mark them so we can re-enable exactly these on reactivation.
                affected = branch.staff_members.filter(is_deleted=False, is_active=True)
                affected_account_ids = list(
                    affected.values_list("admin_user_id", flat=True)
                )
                staff_affected = affected.update(
                    is_active=False, deactivated_by_branch=True
                )
                accounts_affected = AdminUser.objects.filter(
                    id__in=affected_account_ids, is_active=True
                ).update(is_active=False)
            else:
                # Reactivating the branch: only restore staff that were disabled by
                # this branch, leaving individually-disabled staff untouched.
                restorable = branch.staff_members.filter(
                    is_deleted=False, deactivated_by_branch=True
                )
                restorable_account_ids = list(
                    restorable.values_list("admin_user_id", flat=True)
                )
                staff_affected = restorable.update(
                    is_active=True, deactivated_by_branch=False
                )
                accounts_affected = AdminUser.objects.filter(
                    id__in=restorable_account_ids
                ).update(is_active=True)

        self.log_action(
            action=AuditLog.ACTION_BRANCH_UPDATE,
            resource=f"branch:{branch.id}",
            details="Branch active status toggled; staff logins synced.",
            old_value={"is_active": prev_status},
            new_value={
                "is_active": branch.is_active,
                "staff_affected": staff_affected,
                "accounts_affected": accounts_affected,
            },
        )

        return Response({
            "success": True,
            "status": "active" if branch.is_active else "inactive",
            "staff_affected": staff_affected,
            "accounts_affected": accounts_affected,
        })

    def destroy(self, request, *args, **kwargs):
        branch = self.get_object()

        # Example check (replace with subscription model)
        has_active_subscriptions = False

        if has_active_subscriptions:
            return Response(
                {"error": "Cannot delete branch with active subscriptions"},
                status=400
            )

        with transaction.atomic():
            branch.is_deleted = True
            branch.is_active = False
            branch.save(update_fields=["is_deleted", "is_active"])

            # Soft-delete every staff profile and free unique mobiles/emails so
            # those numbers can be reused after the branch is removed.
            staff_to_release = list(
                branch.staff_members.filter(is_deleted=False).select_related("admin_user")
            )
            staff_account_ids = [s.admin_user_id for s in staff_to_release]
            for staff in staff_to_release:
                release_staff_unique_fields(staff)
            staff_deactivated = len(staff_to_release)

            # Disable any remaining staff / branch-manager logins matched by
            # branch code that were not linked through a staff profile above.
            accounts_disabled = AdminUser.objects.filter(
                Q(
                    role__in=[AdminUser.ROLE_BRANCH_MANAGER, AdminUser.ROLE_STAFF],
                    branch__code=branch.code,
                )
                | Q(id__in=staff_account_ids),
                is_active=True,
            ).update(is_active=False)

        self.log_action(
            action=AuditLog.ACTION_BRANCH_UPDATE,
            resource=f"branch:{branch.id}",
            details="Branch soft-deleted; staff and their logins deactivated.",
            old_value={"is_deleted": False},
            new_value={
                "is_deleted": True,
                "staff_deactivated": staff_deactivated,
                "accounts_disabled": accounts_disabled,
            },
        )

        return Response(
            {
                "success": True,
                "staff_deactivated": staff_deactivated,
                "accounts_disabled": accounts_disabled,
            },
            status=status.HTTP_200_OK,
        )

    def perform_update(self, serializer):
        instance = self.get_object()
        old_value = {
            "name": instance.name,
            "city": instance.city,
            "is_active": instance.is_active,
        }
        updated = serializer.save()
        self.log_action(
            action=AuditLog.ACTION_BRANCH_UPDATE,
            resource=f"branch:{updated.id}",
            details="Branch details updated.",
            old_value=old_value,
            new_value={
                "name": updated.name,
                "city": updated.city,
                "is_active": updated.is_active,
            },
        )


# ✅ MOVED OUTSIDE (FIXED INDENTATION)
class BranchSummaryAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        summary = _build_summary_for_branches(Branch.objects.filter(is_deleted=False))

        return Response({
            "success": True,
            "data": summary
        })


class PublicBranchListAPIView(APIView):
    """GET /api/v1/website/branches/ — public office contact details (no token)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        qs = Branch.objects.filter(is_deleted=False, is_active=True).order_by("name", "id")
        serializer = PublicBranchSerializer(qs, many=True)
        return Response({"success": True, "data": serializer.data})