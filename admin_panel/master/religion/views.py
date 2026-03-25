from django.db import transaction
from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from master.models import Caste, Religion
from profiles.models import UserReligion

from .serializers import ReligionListSerializer, ReligionWriteSerializer


def _error(message: str, code: int):
    return Response({"success": False, "error": {"code": code, "message": message}}, status=code)


class ReligionPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


class ReligionListCreateAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = ReligionPagination

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def get(self, request):
        qs = Religion.objects.filter(is_active=True)
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search))
        qs = ReligionListSerializer.setup_eager_loading(qs).order_by("name")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ReligionListSerializer(page, many=True)
        paged = paginator.get_paginated_response(serializer.data).data
        paged["total"] = qs.count()
        return Response({"success": True, "data": paged})

    def post(self, request):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)

        serializer = ReligionWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return _error(serializer.errors.get("name", ["Invalid data"])[0], 400)

        obj = serializer.save(is_active=True)
        data = ReligionListSerializer(
            ReligionListSerializer.setup_eager_loading(Religion.objects.filter(pk=obj.pk)).first()
        ).data
        return Response({"success": True, "data": data}, status=201)


class ReligionDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def _get_obj(self, pk: int):
        return Religion.objects.filter(pk=pk, is_active=True).first()

    def patch(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("Religion not found.", 404)

        serializer = ReligionWriteSerializer(instance=obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return _error(serializer.errors.get("name", ["Invalid data"])[0], 400)
        serializer.save()

        data = ReligionListSerializer(
            ReligionListSerializer.setup_eager_loading(Religion.objects.filter(pk=obj.pk)).first()
        ).data
        return Response({"success": True, "data": data})

    def delete(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("Religion not found.", 404)

        used_count = UserReligion.objects.filter(religion_id=obj.id).count()
        if used_count > 0:
            return _error(
                f"Cannot delete '{obj.name}'. It is used by {used_count} profile(s). Deactivate instead.",
                400,
            )

        with transaction.atomic():
            obj.is_active = False
            obj.save(update_fields=["is_active", "updated_at"])
            Caste.objects.filter(religion_id=obj.id, is_active=True).update(is_active=False)

        return Response({"success": True, "data": {"id": obj.id, "is_active": obj.is_active}})
