from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from master.models import City, District, State
from profiles.models import UserLocation

from admin_panel.master.toggle import MasterToggleStatusAPIView

from .serializers import CityDistrictTabSerializer, CityListSerializer, CityWriteSerializer


def _error(message: str, code: int):
    return Response({"success": False, "error": {"code": code, "message": message}}, status=code)


def _first_error(serializer) -> str:
    for field in ("name", "district", "non_field_errors"):
        if field in serializer.errors and serializer.errors[field]:
            return str(serializer.errors[field][0])
    return "Invalid data"


class CityPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


class CityDistrictTabsAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        state_id = (request.query_params.get("state_id") or "").strip()
        if not state_id:
            return _error("state_id is required to list districts.", 400)
        if not state_id.isdigit():
            return _error("State not found.", 404)

        state = State.objects.filter(pk=int(state_id), is_active=True).first()
        if not state:
            return _error("State not found.", 404)

        qs = District.objects.filter(is_active=True, state_id=state.id).order_by("name")
        qs = CityDistrictTabSerializer.setup_eager_loading(qs)
        serializer = CityDistrictTabSerializer(qs, many=True)
        return Response({"success": True, "data": serializer.data})


class CityListCreateAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = CityPagination

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def get(self, request):
        district_id = (request.query_params.get("district_id") or "").strip()
        if not district_id:
            return _error("district_id is required to list cities.", 400)
        if not district_id.isdigit():
            return _error("District not found.", 404)

        district = District.objects.filter(pk=int(district_id), is_active=True).first()
        if not district:
            return _error("District not found.", 404)

        qs = City.objects.filter(district_id=district.id)
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search))
        qs = qs.select_related("district").order_by("name")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = CityListSerializer(page, many=True)
        paged = paginator.get_paginated_response(serializer.data).data
        paged["total"] = qs.count()
        return Response({"success": True, "data": paged})

    def post(self, request):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)

        serializer = CityWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return _error(_first_error(serializer), 400)

        obj = serializer.save(is_active=True)
        data = CityListSerializer(City.objects.select_related("district").filter(pk=obj.pk).first()).data
        return Response({"success": True, "data": data}, status=201)


class CityDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _is_admin(self, request) -> bool:
        return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN

    def _get_obj(self, pk: int):
        return City.objects.select_related("district").filter(pk=pk, is_active=True).first()

    def patch(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("City not found.", 404)

        serializer = CityWriteSerializer(instance=obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return _error(_first_error(serializer), 400)

        serializer.save()
        obj.refresh_from_db()
        return Response({"success": True, "data": CityListSerializer(obj).data})

    def delete(self, request, pk):
        if not self._is_admin(request):
            return _error("Insufficient permissions", 403)
        obj = self._get_obj(pk)
        if not obj:
            return _error("City not found.", 404)

        used_count = UserLocation.objects.filter(city_id=obj.id).count()
        if used_count > 0:
            return _error(
                f"Cannot delete '{obj.name}'. It is used by {used_count} profile(s). Deactivate instead.",
                400,
            )

        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        return Response({"success": True, "data": {"id": obj.id, "is_active": obj.is_active}})


class CityToggleStatusAPIView(MasterToggleStatusAPIView):
    model = City
    not_found_message = "City not found."

    def get_object(self, pk: int):
        return City.objects.select_related("district").filter(pk=pk).first()

    def serialize(self, obj):
        return CityListSerializer(obj).data
