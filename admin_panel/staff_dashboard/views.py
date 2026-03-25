from __future__ import annotations

from django.db import IntegrityError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.serializers import (
    AdminProfileUpdateSerializer,
    mobile_to_display,
)
from admin_panel.auth.models import AdminUser
from admin_panel.audit_log.serializers import AuditLogSerializer
from admin_panel.audit_log.models import AuditLog

from .services import build_summary_payload, resolve_staff_dashboard_request


class StaffDashboardSummaryAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        staff, err = resolve_staff_dashboard_request(request)
        if err:
            return err
        data = build_summary_payload(staff)
        return Response({"success": True, "data": data})


class StaffDashboardRecentActivityAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _, err = resolve_staff_dashboard_request(request)
        if err:
            return err
        qs = (
            AuditLog.objects.filter(actor=request.user)
            .order_by("-created_at")[:5]
        )
        ser = AuditLogSerializer(qs, many=True)
        return Response({"success": True, "data": {"items": ser.data}})


class StaffDashboardMyProfileAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _payload(self, user: AdminUser, staff) -> dict:
        branch = None
        if getattr(staff, "branch_id", None):
            branch = {
                "id": staff.branch_id,
                "name": getattr(staff.branch, "name", "") or "",
                "code": getattr(staff.branch, "code", "") or "",
            }
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "mobile": user.mobile,
            "mobile_display": mobile_to_display(user.mobile),
            "role": user.role,
            "role_display": user.get_role_display(),
            "branch": branch,
        }

    def get(self, request):
        staff, err = resolve_staff_dashboard_request(request)
        if err:
            return err
        return Response({"success": True, "data": self._payload(request.user, staff)})

    def patch(self, request):
        staff, err = resolve_staff_dashboard_request(request)
        if err:
            return err

        patch_data = {
            "name": request.data.get("name"),
            "email": request.data.get("email"),
        }
        ser = AdminProfileUpdateSerializer(data=patch_data, context={"user": request.user})
        if not ser.is_valid():
            errors = ser.errors
            if "name" in errors:
                return Response(
                    {
                        "success": False,
                        "error": {"code": 400, "message": str(errors["name"][0])},
                    },
                    status=400,
                )
            if "email" in errors:
                return Response(
                    {
                        "success": False,
                        "error": {"code": 400, "message": str(errors["email"][0])},
                    },
                    status=400,
                )
            return Response(
                {"success": False, "error": {"code": 400, "message": "Invalid request"}},
                status=400,
            )

        user = request.user
        user.name = ser.validated_data["name"]
        user.email = ser.validated_data["email"]
        try:
            user.save(update_fields=["name", "email", "updated_at"])
            updates = []
            if staff.name != user.name:
                staff.name = user.name
                updates.append("name")
            if staff.email != user.email:
                staff.email = user.email
                updates.append("email")
            if updates:
                updates.append("updated_at")
                staff.save(update_fields=updates)
        except IntegrityError:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": 400,
                        "message": "Profile email/mobile conflicts with another staff account.",
                    },
                },
                status=400,
            )

        return Response({"success": True, "data": self._payload(user, staff)})
