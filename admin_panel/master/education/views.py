from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from master.models import Education

from admin_panel.master.toggle import MasterToggleStatusAPIView

from .serializers import EducationListSerializer, EducationWriteSerializer


def _error(message: str, code: int):
    return Response(
        {"success": False, "message": message, "error": {"code": code, "message": message}},
        status=code,
    )


def _ok(data, message: str = "Data fetched successfully", status: int = 200):
    return Response({"success": True, "message": message, "data": data}, status=status)


class EducationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


class EducationListCreateAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = EducationPagination

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def get(self, request):
        qs = Education.objects.all()
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search))
        qs = qs.order_by("-created_at")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = EducationListSerializer(page, many=True)
        paged = paginator.get_paginated_response(serializer.data).data
        paged["total"] = qs.count()
        return _ok(paged, message="Data fetched successfully")

    def post(self, request):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)

        serializer = EducationWriteSerializer(data=request.data)
        if not serializer.is_valid():
            for field in ("name", "non_field_errors"):
                if field in serializer.errors and serializer.errors[field]:
                    return _error(str(serializer.errors[field][0]), 400)
            return _error("Invalid data", 400)

        obj = serializer.save(is_active=True)
        data = EducationListSerializer(obj).data
        return _ok(data, message="Education created successfully", status=201)


class EducationDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def _get_obj(self, pk: int):
        return Education.objects.filter(pk=pk, is_active=True).first()

    def patch(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("Education not found.", 404)

        serializer = EducationWriteSerializer(instance=obj, data=request.data, partial=True)
        if not serializer.is_valid():
            for field in ("name", "non_field_errors"):
                if field in serializer.errors and serializer.errors[field]:
                    return _error(str(serializer.errors[field][0]), 400)
            return _error("Invalid data", 400)

        serializer.save()
        obj.refresh_from_db()
        return _ok(
            EducationListSerializer(obj).data,
            message="Education updated successfully",
        )

    def delete(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("Education not found.", 404)

        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        return _ok(
            {"id": obj.id, "is_active": obj.is_active},
            message="Education deactivated successfully",
        )


class EducationToggleStatusAPIView(MasterToggleStatusAPIView):
    model = Education
    not_found_message = "Education not found."
    include_message = True

    def serialize(self, obj):
        return EducationListSerializer(obj).data
