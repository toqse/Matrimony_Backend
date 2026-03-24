from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from master.models import MotherTongue
from profiles.models import UserReligion

from .serializers import MotherTongueSerializer


def _error(message: str, code: int):
    return Response({"success": False, "error": {"code": code, "message": message}}, status=code)


class MotherTonguePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


class MotherTongueListCreateAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = MotherTonguePagination

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def get(self, request):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)

        qs = MotherTongue.objects.filter(is_active=True)
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search))
        qs = qs.order_by("name")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = MotherTongueSerializer(page, many=True)
        paged = paginator.get_paginated_response(serializer.data)
        return Response({"success": True, "data": paged.data})

    def post(self, request):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)

        serializer = MotherTongueSerializer(data=request.data)
        if not serializer.is_valid():
            return _error(serializer.errors.get("name", ["Invalid data"])[0], 400)

        obj = serializer.save(is_active=True)
        return Response({"success": True, "data": MotherTongueSerializer(obj).data}, status=201)


class MotherTongueDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def _get_obj(self, pk: int):
        return MotherTongue.objects.filter(pk=pk, is_active=True).first()

    def patch(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("Mother tongue not found.", 404)

        serializer = MotherTongueSerializer(instance=obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return _error(serializer.errors.get("name", ["Invalid data"])[0], 400)
        serializer.save()
        return Response({"success": True, "data": serializer.data})

    def delete(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("Mother tongue not found.", 404)

        used_count = UserReligion.objects.filter(mother_tongue_id=obj.id).count()
        if used_count > 0:
            return _error(
                f"Cannot delete '{obj.name}'. It is used by {used_count} profile(s). Deactivate instead.",
                400,
            )

        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        return Response({"success": True, "data": {"id": obj.id, "is_active": obj.is_active}})
