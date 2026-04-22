from datetime import datetime

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.pagination import StandardPagination
from admin_panel.permissions import IsAdminUser

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogListAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        qs = AuditLog.objects.all().order_by("-created_at")

        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(actor_name__icontains=search)
                | Q(resource__icontains=search)
                | Q(details__icontains=search)
                | Q(branch_name__icontains=search)
                | Q(staff_name__icontains=search)
                | Q(target_profile_name__icontains=search)
            )

        action = (request.query_params.get("action") or "").strip()
        if action:
            valid_actions = {choice[0] for choice in AuditLog.ACTION_CHOICES}
            if action not in valid_actions:
                return Response(
                    {"success": False, "error": {"code": 400, "message": "Invalid action filter."}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(action=action)

        action_type = (request.query_params.get("action_type") or "").strip()
        if action_type:
            valid_types = {c[0] for c in AuditLog.ACTION_TYPE_CHOICES}
            if action_type not in valid_types:
                return Response(
                    {"success": False, "error": {"code": 400, "message": "Invalid action_type filter."}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(action_type=action_type)

        role = (request.query_params.get("role") or "").strip()
        if role:
            valid_roles = {
                AdminUser.ROLE_ADMIN,
                AdminUser.ROLE_BRANCH_MANAGER,
                AdminUser.ROLE_STAFF,
            }
            if role not in valid_roles:
                return Response(
                    {"success": False, "error": {"code": 400, "message": "Invalid role."}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(Q(role=role) | Q(actor_role=role))

        start_date = (request.query_params.get("start_date") or request.query_params.get("from_date") or "").strip()
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%d-%m-%Y").date()
            except ValueError:
                return Response(
                    {"success": False, "error": {"code": 400, "message": "Invalid date format (-)."}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(created_at__date__gte=start_dt)

        end_date = (request.query_params.get("end_date") or request.query_params.get("to_date") or "").strip()
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%d-%m-%Y").date()
            except ValueError:
                return Response(
                    {"success": False, "error": {"code": 400, "message": "Invalid date format (-)."}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(created_at__date__lte=end_dt)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AuditLogSerializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        return Response({"success": True, "data": response.data}, status=status.HTTP_200_OK)


class AuditLogActionOptionsAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        actions = [
            {"value": value, "label": label}
            for value, label in AuditLog.ACTION_CHOICES
        ]
        roles = [
            {"value": value, "label": label}
            for value, label in AdminUser.ROLE_CHOICES
        ]
        role_values = {r["value"] for r in roles}

        # Prefer names captured in audit trail; fallback to AdminUser names.
        actor_names = list(
            AuditLog.objects.exclude(actor_name__exact="")
            .order_by("actor_name")
            .values_list("actor_name", flat=True)
            .distinct()
        )
        if not actor_names:
            actor_names = list(
                AdminUser.objects.exclude(name__exact="")
                .order_by("name")
                .values_list("name", flat=True)
                .distinct()
            )
        usernames = [{"value": n, "label": n} for n in actor_names]

        # Include any role values seen in historical logs (for old/legacy rows).
        legacy_roles = set(
            AuditLog.objects.exclude(role__exact="")
            .values_list("role", flat=True)
            .distinct()
        ) | set(
            AuditLog.objects.exclude(actor_role__exact="")
            .values_list("actor_role", flat=True)
            .distinct()
        )
        for value in sorted(legacy_roles):
            if value not in role_values:
                roles.append({"value": value, "label": value.replace("_", " ").title()})

        action_types = [
            {"value": value, "label": label}
            for value, label in AuditLog.ACTION_TYPE_CHOICES
        ]

        return Response(
            {
                "success": True,
                "data": {
                    "actions": actions,
                    "action_types": action_types,
                    "roles": roles,
                    "usernames": usernames,
                },
            },
            status=status.HTTP_200_OK,
        )
