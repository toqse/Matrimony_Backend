from decimal import Decimal

from django.db.models import Count, Sum, Q
from django.db.models.functions import Coalesce
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.audit_log.mixins import AuditLogMixin
from admin_panel.audit_log.models import AuditLog
from plans.models import Transaction
from .models import Branch
from .serializers import BranchSerializer


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

        return queryset

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

        # Example check (replace with real staff relation)
        has_active_staff = False

        # FIXED LOGIC
        if branch.is_active and has_active_staff:
            return Response(
                {"error": "Deactivate or reassign staff before deactivating branch"},
                status=400
            )

        prev_status = branch.is_active
        branch.is_active = not branch.is_active
        branch.save()
        self.log_action(
            action=AuditLog.ACTION_BRANCH_UPDATE,
            resource=f"branch:{branch.id}",
            details="Branch active status toggled.",
            old_value={"is_active": prev_status},
            new_value={"is_active": branch.is_active},
        )

        return Response({
            "success": True,
            "status": "active" if branch.is_active else "inactive"
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

        branch.is_deleted = True
        branch.save()
        self.log_action(
            action=AuditLog.ACTION_BRANCH_UPDATE,
            resource=f"branch:{branch.id}",
            details="Branch soft-deleted.",
            old_value={"is_deleted": False},
            new_value={"is_deleted": True},
        )

        return Response({"success": True}, status=status.HTTP_200_OK)

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