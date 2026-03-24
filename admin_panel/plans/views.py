from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from plans.models import Plan, UserPlan

from .serializers import AdminPlanSerializer


class AdminPlanAccessPermission(BasePermission):
    """
    Admin: full CRUD
    Branch manager/staff: read-only
    """

    def has_permission(self, request, view):
        user = request.user
        role = getattr(user, "role", None)
        if role not in {AdminUser.ROLE_ADMIN, AdminUser.ROLE_BRANCH_MANAGER, AdminUser.ROLE_STAFF}:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return role == AdminUser.ROLE_ADMIN


class AdminPlansViewSet(viewsets.ModelViewSet):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, AdminPlanAccessPermission]
    serializer_class = AdminPlanSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        today = timezone.localdate()
        return (
            Plan.objects.all()
            .annotate(
                subscriber_count=Count(
                    "user_plans",
                    filter=Q(user_plans__is_active=True, user_plans__valid_until__gte=today),
                )
            )
            .order_by("price", "id")
        )

    def list(self, request, *args, **kwargs):
        ser = self.get_serializer(self.get_queryset(), many=True)
        return Response({"success": True, "data": ser.data})

    def retrieve(self, request, *args, **kwargs):
        ser = self.get_serializer(self.get_object())
        return Response({"success": True, "data": ser.data})

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = ser.save()
        return Response({"success": True, "data": self.get_serializer(obj).data}, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        obj = self.get_object()
        ser = self.get_serializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        obj = ser.save()
        return Response({"success": True, "data": self.get_serializer(obj).data})

    @action(detail=True, methods=["patch"], url_path="toggle-status")
    def toggle_status(self, request, pk=None):
        plan = self.get_object()
        if plan.is_active:
            active_count = UserPlan.objects.filter(
                plan=plan, is_active=True, valid_until__gte=timezone.localdate()
            ).count()
            if active_count > 0:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": 400,
                            "message": f"Cannot deactivate a plan with active subscribers ({active_count} subscribers)",
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        plan.is_active = not plan.is_active
        plan.save(update_fields=["is_active", "updated_at"])
        return Response(
            {
                "success": True,
                "data": {
                    "id": plan.id,
                    "is_active": plan.is_active,
                    "status": "active" if plan.is_active else "inactive",
                },
            }
        )
