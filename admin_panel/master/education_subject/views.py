from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from master.models import EducationSubject

from .serializers import EducationSubjectListSerializer, EducationSubjectWriteSerializer


def _error(message: str, code: int):
    return Response(
        {"success": False, "message": message, "error": {"code": code, "message": message}},
        status=code,
    )


def _ok(data, message: str = "Data fetched successfully", status: int = 200):
    return Response({"success": True, "message": message, "data": data}, status=status)


class EducationSubjectPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


class EducationSubjectListCreateAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = EducationSubjectPagination

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def get(self, request):
        qs = EducationSubject.objects.filter(is_active=True).prefetch_related("educations")
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search))
        qs = qs.order_by("-created_at")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = EducationSubjectListSerializer(page, many=True)
        paged = paginator.get_paginated_response(serializer.data).data
        paged["total"] = qs.count()
        return _ok(paged, message="Data fetched successfully")

    def post(self, request):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)

        serializer = EducationSubjectWriteSerializer(data=request.data)
        if not serializer.is_valid():
            for field in ("name", "educations", "non_field_errors"):
                if field in serializer.errors and serializer.errors[field]:
                    err = serializer.errors[field]
                    return _error(str(err[0] if isinstance(err, list) else err), 400)
            return _error("Invalid data", 400)

        obj = serializer.save(is_active=True)
        data = EducationSubjectListSerializer(
            EducationSubject.objects.filter(pk=obj.pk).prefetch_related("educations").first()
        ).data
        return _ok(data, message="Education subject created successfully", status=201)


class EducationSubjectDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def _get_obj(self, pk: int):
        return (
            EducationSubject.objects.filter(pk=pk, is_active=True)
            .prefetch_related("educations")
            .first()
        )

    def patch(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("Education subject not found.", 404)

        serializer = EducationSubjectWriteSerializer(
            instance=obj, data=request.data, partial=True
        )
        if not serializer.is_valid():
            for field in ("name", "educations", "non_field_errors"):
                if field in serializer.errors and serializer.errors[field]:
                    err = serializer.errors[field]
                    return _error(str(err[0] if isinstance(err, list) else err), 400)
            return _error("Invalid data", 400)

        serializer.save()
        obj.refresh_from_db()
        return _ok(
            EducationSubjectListSerializer(obj).data,
            message="Education subject updated successfully",
        )

    def delete(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("Education subject not found.", 404)

        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        return _ok(
            {"id": obj.id, "is_active": obj.is_active},
            message="Education subject deactivated successfully",
        )
