from django.db import transaction
from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from master.cache_utils import (
    RESOURCE_CITIES,
    RESOURCE_DISTRICTS,
    RESOURCE_STATES,
    invalidate_master_resources,
)
from master.models import City, Country, District, State
from profiles.models import UserLocation

from admin_panel.master.toggle import MasterToggleStatusAPIView

from .serializers import StateCountryTabSerializer, StateListSerializer, StateWriteSerializer


def _error(message: str, code: int):
    return Response({"success": False, "error": {"code": code, "message": message}}, status=code)


def _first_error(serializer) -> str:
    for field in ("name", "code", "country", "non_field_errors"):
        if field in serializer.errors and serializer.errors[field]:
            return str(serializer.errors[field][0])
    return "Invalid data"


class StatePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


class StateCountryTabsAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Country.objects.filter(is_active=True).order_by("name")
        qs = StateCountryTabSerializer.setup_eager_loading(qs)
        serializer = StateCountryTabSerializer(qs, many=True)
        return Response({"success": True, "data": serializer.data})


class StateListCreateAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = StatePagination

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def get(self, request):
        country_id = (request.query_params.get("country_id") or "").strip()
        if not country_id:
            return _error("country_id is required to list states.", 400)
        if not country_id.isdigit():
            return _error("Country not found.", 404)

        country = Country.objects.filter(pk=int(country_id), is_active=True).first()
        if not country:
            return _error("Country not found.", 404)

        qs = State.objects.filter(country_id=country.id)
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        qs = qs.select_related("country").order_by("name")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = StateListSerializer(page, many=True)
        paged = paginator.get_paginated_response(serializer.data).data
        paged["total"] = qs.count()
        return Response({"success": True, "data": paged})

    def post(self, request):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)

        serializer = StateWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return _error(_first_error(serializer), 400)

        obj = serializer.save(is_active=True)
        data = StateListSerializer(State.objects.select_related("country").filter(pk=obj.pk).first()).data
        return Response({"success": True, "data": data}, status=201)


class StateDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def _get_obj(self, pk: int):
        return State.objects.select_related("country").filter(pk=pk, is_active=True).first()

    def patch(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("State not found.", 404)

        serializer = StateWriteSerializer(instance=obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return _error(_first_error(serializer), 400)

        serializer.save()
        obj.refresh_from_db()
        return Response({"success": True, "data": StateListSerializer(obj).data})

    def delete(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("State not found.", 404)

        used_count = UserLocation.objects.filter(state_id=obj.id).count()
        if used_count > 0:
            return _error(
                f"Cannot delete '{obj.name}'. It is used by {used_count} profile(s). Deactivate instead.",
                400,
            )

        with transaction.atomic():
            obj.is_active = False
            obj.save(update_fields=["is_active", "updated_at"])
            district_ids = list(
                District.objects.filter(state_id=obj.id, is_active=True).values_list("id", flat=True)
            )
            District.objects.filter(id__in=district_ids).update(is_active=False)
            City.objects.filter(district_id__in=district_ids, is_active=True).update(is_active=False)

        invalidate_master_resources(RESOURCE_STATES, RESOURCE_DISTRICTS, RESOURCE_CITIES)
        return Response({"success": True, "data": {"id": obj.id, "is_active": obj.is_active}})


class StateToggleStatusAPIView(MasterToggleStatusAPIView):
    model = State
    not_found_message = "State not found."

    def get_object(self, pk: int):
        return State.objects.select_related("country").filter(pk=pk).first()

    def serialize(self, obj):
        return StateListSerializer(obj).data

    def cascade_deactivate(self, obj):
        district_ids = list(
            District.objects.filter(state_id=obj.id, is_active=True).values_list("id", flat=True)
        )
        District.objects.filter(id__in=district_ids).update(is_active=False)
        City.objects.filter(district_id__in=district_ids, is_active=True).update(is_active=False)

    def invalidate(self, obj, activating: bool):
        if not activating:
            invalidate_master_resources(RESOURCE_STATES, RESOURCE_DISTRICTS, RESOURCE_CITIES)
