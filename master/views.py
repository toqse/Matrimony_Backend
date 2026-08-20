"""
Master dropdown APIs with live search (optional ?search=).
CRUD ViewSets for Religion, Caste, MotherTongue (admin write, all read).
"""
from rest_framework import generics, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.filters import SearchFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q

from core.permissions import ReadOnlyOrAdmin
from . import cache_utils as mc
from .filters import CasteFilter
from .models import (
    Country, State, District, City,
    Religion, Caste, MotherTongue, Height, MaritalStatus, Complexion, IncomeRange,
    Education, EducationSubject, Occupation, EmploymentStatus,
)
from .serializers import (
    CountrySerializer, StateSerializer, DistrictSerializer, CitySerializer,
    ReligionSerializer, CasteSerializer, MotherTongueSerializer, HeightSerializer,
    MaritalStatusSerializer, ComplexionSerializer, IncomeRangeSerializer,
    EducationSerializer, EducationSubjectSerializer, OccupationSerializer,
    EmploymentStatusSerializer,
)


class MasterListPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'limit'
    max_page_size = 200


class CachedMasterListMixin:
    """Cache-aside for public master list GET responses (identical payload)."""
    master_cache_resource = None

    def list(self, request, *args, **kwargs):
        resource = getattr(self, 'master_cache_resource', None)
        if not resource:
            return super().list(request, *args, **kwargs)
        query_string = request.META.get('QUERY_STRING', '') or ''
        cached = mc.get_cached_master_list(resource, query_string)
        if cached is not None:
            return Response(cached)
        response = super().list(request, *args, **kwargs)
        if getattr(response, 'status_code', 200) == 200 and hasattr(response, 'data'):
            mc.set_cached_master_list(resource, query_string, response.data)
        return response


class CountryList(CachedMasterListMixin, generics.ListAPIView):
    master_cache_resource = mc.RESOURCE_COUNTRIES
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = CountrySerializer
    pagination_class = MasterListPagination

    def get_queryset(self):
        qs = Country.objects.filter(is_active=True).order_by('name')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return qs


class StateList(CachedMasterListMixin, generics.ListAPIView):
    master_cache_resource = mc.RESOURCE_STATES
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = StateSerializer
    pagination_class = MasterListPagination

    def get_queryset(self):
        qs = State.objects.filter(is_active=True).select_related('country').order_by('name')
        country_id = self.request.query_params.get('country_id')
        if country_id:
            qs = qs.filter(country_id=country_id)
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class DistrictList(CachedMasterListMixin, generics.ListAPIView):
    master_cache_resource = mc.RESOURCE_DISTRICTS
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = DistrictSerializer
    pagination_class = MasterListPagination

    def get_queryset(self):
        qs = District.objects.filter(is_active=True).select_related('state').order_by('name')
        state_id = self.request.query_params.get('state_id')
        if state_id:
            qs = qs.filter(state_id=state_id)
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class CityList(CachedMasterListMixin, generics.ListAPIView):
    master_cache_resource = mc.RESOURCE_CITIES
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = CitySerializer
    pagination_class = MasterListPagination

    def get_queryset(self):
        qs = City.objects.filter(is_active=True).select_related('district').order_by('name')
        district_ids = []
        seen = set()
        for raw in self.request.query_params.getlist('district_id'):
            for part in str(raw).split(','):
                s = part.strip()
                if s.isdigit():
                    val = int(s)
                    if val not in seen:
                        seen.add(val)
                        district_ids.append(val)
        for raw in self.request.query_params.getlist('district_ids'):
            for part in str(raw).split(','):
                s = part.strip()
                if s.isdigit():
                    val = int(s)
                    if val not in seen:
                        seen.add(val)
                        district_ids.append(val)
        if district_ids:
            qs = qs.filter(district_id__in=district_ids)
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class ReligionList(CachedMasterListMixin, generics.ListAPIView):
    master_cache_resource = mc.RESOURCE_RELIGIONS
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = ReligionSerializer
    pagination_class = MasterListPagination

    def get_queryset(self):
        qs = Religion.objects.filter(is_active=True).order_by('name')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class MotherTongueList(CachedMasterListMixin, generics.ListAPIView):
    master_cache_resource = mc.RESOURCE_MOTHER_TONGUES
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = MotherTongueSerializer
    pagination_class = MasterListPagination

    def get_queryset(self):
        qs = MotherTongue.objects.filter(is_active=True).order_by('name')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class HeightList(CachedMasterListMixin, generics.ListAPIView):
    master_cache_resource = mc.RESOURCE_HEIGHTS
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = HeightSerializer
    pagination_class = MasterListPagination

    def get_queryset(self):
        return Height.objects.filter(is_active=True).order_by('value_cm')


class MaritalStatusList(CachedMasterListMixin, generics.ListAPIView):
    master_cache_resource = mc.RESOURCE_MARITAL_STATUSES
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = MaritalStatusSerializer
    pagination_class = MasterListPagination

    def get_queryset(self):
        return MaritalStatus.objects.filter(is_active=True).order_by('name')


class ComplexionList(CachedMasterListMixin, generics.ListAPIView):
    master_cache_resource = mc.RESOURCE_COMPLEXIONS
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = ComplexionSerializer
    pagination_class = MasterListPagination

    def get_queryset(self):
        return Complexion.active_valid_queryset().order_by('name')


class IncomeRangeList(CachedMasterListMixin, generics.ListAPIView):
    master_cache_resource = mc.RESOURCE_INCOME_RANGES
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = IncomeRangeSerializer
    pagination_class = MasterListPagination

    def get_queryset(self):
        return IncomeRange.objects.filter(is_active=True).order_by('min_value')


class EducationList(CachedMasterListMixin, generics.ListAPIView):
    master_cache_resource = mc.RESOURCE_EDUCATIONS
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = EducationSerializer
    pagination_class = MasterListPagination

    def get_queryset(self):
        qs = Education.objects.filter(is_active=True).order_by('name')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class EducationSubjectList(CachedMasterListMixin, generics.ListAPIView):
    master_cache_resource = mc.RESOURCE_EDUCATION_SUBJECTS
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = EducationSubjectSerializer
    pagination_class = MasterListPagination

    def get_queryset(self):
        qs = EducationSubject.objects.filter(is_active=True).order_by('name')
        education_id = self.request.query_params.get('education_id')
        if education_id:
            qs = qs.filter(educations__id=education_id, educations__is_active=True)
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs.distinct()


class OccupationList(CachedMasterListMixin, generics.ListAPIView):
    master_cache_resource = mc.RESOURCE_OCCUPATIONS
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = OccupationSerializer
    pagination_class = MasterListPagination

    def get_queryset(self):
        qs = Occupation.objects.filter(is_active=True).order_by('name')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class EmploymentStatusList(CachedMasterListMixin, generics.ListAPIView):
    master_cache_resource = mc.RESOURCE_EMPLOYMENT_STATUSES
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = EmploymentStatusSerializer
    pagination_class = MasterListPagination

    def get_queryset(self):
        qs = EmploymentStatus.objects.filter(is_active=True).order_by('name')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


# --- CRUD ViewSets (Admin create/update/delete; everyone can read) ---

class ReligionViewSet(CachedMasterListMixin, viewsets.ModelViewSet):
    master_cache_resource = mc.RESOURCE_RELIGIONS
    serializer_class = ReligionSerializer
    permission_classes = [ReadOnlyOrAdmin]
    authentication_classes = []
    pagination_class = MasterListPagination
    filter_backends = [SearchFilter]
    search_fields = ['name']

    def get_queryset(self):
        qs = Religion.objects.all().order_by('name')
        user = self.request.user
        if user.is_authenticated and getattr(user, 'role', None) == 'admin':
            return qs
        return qs.filter(is_active=True)


class CasteViewSet(CachedMasterListMixin, viewsets.ModelViewSet):
    master_cache_resource = mc.RESOURCE_CASTES
    serializer_class = CasteSerializer
    permission_classes = [ReadOnlyOrAdmin]
    authentication_classes = []
    pagination_class = MasterListPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = CasteFilter
    search_fields = ['name']

    def get_queryset(self):
        qs = Caste.objects.all().select_related('religion').order_by('name')
        user = self.request.user
        if user.is_authenticated and getattr(user, 'role', None) == 'admin':
            return qs
        return qs.filter(is_active=True, religion__is_active=True)


class MotherTongueViewSet(CachedMasterListMixin, viewsets.ModelViewSet):
    master_cache_resource = mc.RESOURCE_MOTHER_TONGUES
    serializer_class = MotherTongueSerializer
    permission_classes = [ReadOnlyOrAdmin]
    authentication_classes = []
    pagination_class = MasterListPagination
    filter_backends = [SearchFilter]
    search_fields = ['name']

    def get_queryset(self):
        qs = MotherTongue.objects.all().order_by('name')
        user = self.request.user
        if user.is_authenticated and getattr(user, 'role', None) == 'admin':
            return qs
        return qs.filter(is_active=True)
