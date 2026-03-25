from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from master.models import Caste, Religion
from profiles.models import UserReligion

from .serializers import CasteListSerializer, CasteReligionTabSerializer, CasteWriteSerializer


def _error(message: str, code: int):
    return Response({"success": False, "error": {"code": code, "message": message}}, status=code)


class CastePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


class CasteReligionTabsAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def get(self, request):
        qs = Religion.objects.filter(is_active=True).order_by("name")
        qs = CasteReligionTabSerializer.setup_eager_loading(qs)
        serializer = CasteReligionTabSerializer(qs, many=True)
        return Response({"success": True, "data": serializer.data})


class CasteListCreateAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = CastePagination

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def get(self, request):
        religion_id = (request.query_params.get("religion_id") or "").strip()
        if not religion_id:
            return _error("religion_id is required to list castes.", 400)
        if not religion_id.isdigit():
            return _error("Religion not found.", 404)

        religion = Religion.objects.filter(pk=int(religion_id), is_active=True).first()
        if not religion:
            return _error("Religion not found.", 404)

        qs = Caste.objects.filter(is_active=True, religion_id=religion.id)
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search))
        qs = qs.select_related("religion").order_by("name")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = CasteListSerializer(page, many=True)
        paged = paginator.get_paginated_response(serializer.data).data
        paged["total"] = qs.count()
        return Response({"success": True, "data": paged})

    def post(self, request):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)

        serializer = CasteWriteSerializer(data=request.data)
        if not serializer.is_valid():
            for field in ("name", "religion", "non_field_errors"):
                if field in serializer.errors and serializer.errors[field]:
                    return _error(str(serializer.errors[field][0]), 400)
            return _error("Invalid data", 400)

        obj = serializer.save(is_active=True)
        data = CasteListSerializer(Caste.objects.select_related("religion").filter(pk=obj.pk).first()).data
        return Response({"success": True, "data": data}, status=201)


class CasteDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def _get_obj(self, pk: int):
        return Caste.objects.select_related("religion").filter(pk=pk, is_active=True).first()

    def patch(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("Caste not found.", 404)

        serializer = CasteWriteSerializer(instance=obj, data=request.data, partial=True)
        if not serializer.is_valid():
            for field in ("name", "religion", "non_field_errors"):
                if field in serializer.errors and serializer.errors[field]:
                    return _error(str(serializer.errors[field][0]), 400)
            return _error("Invalid data", 400)

        serializer.save()
        obj.refresh_from_db()
        return Response({"success": True, "data": CasteListSerializer(obj).data})

    def delete(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("Caste not found.", 404)

        used_count = UserReligion.objects.filter(caste_fk_id=obj.id).count()
        if used_count > 0:
            return _error(
                f"Cannot delete '{obj.name}'. It is used by {used_count} profile(s). Deactivate instead.",
                400,
            )

        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        return Response({"success": True, "data": {"id": obj.id, "is_active": obj.is_active}})
