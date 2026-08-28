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
    RESOURCE_COUNTRIES,
    RESOURCE_DISTRICTS,
    RESOURCE_STATES,
    invalidate_master_resources,
)
from master.models import City, Country, District, State
from profiles.models import UserLocation

from admin_panel.master.toggle import MasterToggleStatusAPIView

from .serializers import CountryListSerializer, CountryWriteSerializer


def _error(message: str, code: int):
    return Response({"success": False, "error": {"code": code, "message": message}}, status=code)


def _first_error(serializer) -> str:
    for field in ("name", "code", "non_field_errors"):
        if field in serializer.errors and serializer.errors[field]:
            return str(serializer.errors[field][0])
    return "Invalid data"


class CountryPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


class CountryListCreateAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = CountryPagination

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def get(self, request):
        qs = Country.objects.all()
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        qs = CountryListSerializer.setup_eager_loading(qs).order_by("name")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = CountryListSerializer(page, many=True)
        paged = paginator.get_paginated_response(serializer.data).data
        paged["total"] = qs.count()
        return Response({"success": True, "data": paged})

    def post(self, request):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)

        serializer = CountryWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return _error(_first_error(serializer), 400)

        obj = serializer.save(is_active=True)
        data = CountryListSerializer(
            CountryListSerializer.setup_eager_loading(Country.objects.filter(pk=obj.pk)).first()
        ).data
        return Response({"success": True, "data": data}, status=201)


class CountryDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def _get_obj(self, pk: int):
        return Country.objects.filter(pk=pk, is_active=True).first()

    def patch(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("Country not found.", 404)

        serializer = CountryWriteSerializer(instance=obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return _error(_first_error(serializer), 400)
        serializer.save()

        data = CountryListSerializer(
            CountryListSerializer.setup_eager_loading(Country.objects.filter(pk=obj.pk)).first()
        ).data
        return Response({"success": True, "data": data})

    def delete(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("Country not found.", 404)

        used_count = UserLocation.objects.filter(country_id=obj.id).count()
        if used_count > 0:
            return _error(
                f"Cannot delete '{obj.name}'. It is used by {used_count} profile(s). Deactivate instead.",
                400,
            )

        with transaction.atomic():
            obj.is_active = False
            obj.save(update_fields=["is_active", "updated_at"])
            state_ids = list(State.objects.filter(country_id=obj.id, is_active=True).values_list("id", flat=True))
            district_ids = list(
                District.objects.filter(state_id__in=state_ids, is_active=True).values_list("id", flat=True)
            )
            State.objects.filter(id__in=state_ids).update(is_active=False)
            District.objects.filter(id__in=district_ids).update(is_active=False)
            City.objects.filter(district_id__in=district_ids, is_active=True).update(is_active=False)

        invalidate_master_resources(
            RESOURCE_COUNTRIES, RESOURCE_STATES, RESOURCE_DISTRICTS, RESOURCE_CITIES
        )
        return Response({"success": True, "data": {"id": obj.id, "is_active": obj.is_active}})


class CountryToggleStatusAPIView(MasterToggleStatusAPIView):
    model = Country
    not_found_message = "Country not found."

    def serialize(self, obj):
        return CountryListSerializer(
            CountryListSerializer.setup_eager_loading(Country.objects.filter(pk=obj.pk)).first()
        ).data

    def cascade_deactivate(self, obj):
        state_ids = list(State.objects.filter(country_id=obj.id, is_active=True).values_list("id", flat=True))
        district_ids = list(
            District.objects.filter(state_id__in=state_ids, is_active=True).values_list("id", flat=True)
        )
        State.objects.filter(id__in=state_ids).update(is_active=False)
        District.objects.filter(id__in=district_ids).update(is_active=False)
        City.objects.filter(district_id__in=district_ids, is_active=True).update(is_active=False)

    def invalidate(self, obj, activating: bool):
        if not activating:
            invalidate_master_resources(
                RESOURCE_COUNTRIES, RESOURCE_STATES, RESOURCE_DISTRICTS, RESOURCE_CITIES
            )
