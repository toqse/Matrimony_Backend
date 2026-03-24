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
            qs = qs.filter(actor_role=role)

        start_date = (request.query_params.get("start_date") or "").strip()
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%d-%m-%Y").date()
            except ValueError:
                return Response(
                    {"success": False, "error": {"code": 400, "message": "Invalid date format (-)."}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(created_at__date__gte=start_dt)

        end_date = (request.query_params.get("end_date") or "").strip()
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
        return Response({"success": True, "data": actions}, status=status.HTTP_200_OK)
