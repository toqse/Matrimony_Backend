"""
Master dropdown APIs with live search (optional ?search=).
CRUD ViewSets for Religion, Caste, MotherTongue (admin write, all read).
"""
from rest_framework import generics, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.filters import SearchFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q

from core.permissions import ReadOnlyOrAdmin
from .filters import CasteFilter
from .models import (
    Country, State, District, City,
    Religion, Caste, MotherTongue, Height, MaritalStatus, IncomeRange,
    Education, EducationSubject, Occupation, EmploymentStatus,
)
from .serializers import (
    CountrySerializer, StateSerializer, DistrictSerializer, CitySerializer,
    ReligionSerializer, CasteSerializer, MotherTongueSerializer, HeightSerializer,
    MaritalStatusSerializer, IncomeRangeSerializer,
    EducationSerializer, EducationSubjectSerializer, OccupationSerializer,
    EmploymentStatusSerializer,
)


class CountryList(generics.ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = CountrySerializer

    def get_queryset(self):
        qs = Country.objects.filter(is_active=True).order_by('name')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return qs


class StateList(generics.ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = StateSerializer

    def get_queryset(self):
        qs = State.objects.filter(is_active=True).select_related('country').order_by('name')
        country_id = self.request.query_params.get('country_id')
        if country_id:
            qs = qs.filter(country_id=country_id)
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class DistrictList(generics.ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = DistrictSerializer

    def get_queryset(self):
        qs = District.objects.filter(is_active=True).select_related('state').order_by('name')
        state_id = self.request.query_params.get('state_id')
        if state_id:
            qs = qs.filter(state_id=state_id)
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class CityList(generics.ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = CitySerializer

    def get_queryset(self):
        qs = City.objects.filter(is_active=True).select_related('district').order_by('name')
        district_id = self.request.query_params.get('district_id')
        if district_id:
            qs = qs.filter(district_id=district_id)
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class ReligionList(generics.ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = ReligionSerializer

    def get_queryset(self):
        qs = Religion.objects.filter(is_active=True).order_by('name')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class MotherTongueList(generics.ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = MotherTongueSerializer

    def get_queryset(self):
        qs = MotherTongue.objects.filter(is_active=True).order_by('name')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class HeightList(generics.ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = HeightSerializer

    def get_queryset(self):
        return Height.objects.filter(is_active=True).order_by('value_cm')


class MaritalStatusList(generics.ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = MaritalStatusSerializer

    def get_queryset(self):
        return MaritalStatus.objects.filter(is_active=True).order_by('name')


class IncomeRangeList(generics.ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = IncomeRangeSerializer

    def get_queryset(self):
        return IncomeRange.objects.filter(is_active=True).order_by('min_value')


class EducationList(generics.ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = EducationSerializer

    def get_queryset(self):
        qs = Education.objects.filter(is_active=True).order_by('name')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class EducationSubjectList(generics.ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = EducationSubjectSerializer

    def get_queryset(self):
        qs = EducationSubject.objects.filter(is_active=True).order_by('name')
        education_id = self.request.query_params.get('education_id')
        if education_id:
            qs = qs.filter(educations__id=education_id, educations__is_active=True)
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs.distinct()


class OccupationList(generics.ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = OccupationSerializer

    def get_queryset(self):
        qs = Occupation.objects.filter(is_active=True).order_by('name')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class EmploymentStatusList(generics.ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = EmploymentStatusSerializer

    def get_queryset(self):
        qs = EmploymentStatus.objects.filter(is_active=True).order_by('name')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


# --- CRUD ViewSets (Admin create/update/delete; everyone can read) ---

class ReligionViewSet(viewsets.ModelViewSet):
    serializer_class = ReligionSerializer
    permission_classes = [ReadOnlyOrAdmin]
    authentication_classes = []
    filter_backends = [SearchFilter]
    search_fields = ['name']

    def get_queryset(self):
        qs = Religion.objects.all().order_by('name')
        user = self.request.user
        if user.is_authenticated and getattr(user, 'role', None) == 'admin':
            return qs
        return qs.filter(is_active=True)


class CasteViewSet(viewsets.ModelViewSet):
    serializer_class = CasteSerializer
    permission_classes = [ReadOnlyOrAdmin]
    authentication_classes = []
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = CasteFilter
    search_fields = ['name']

    def get_queryset(self):
        qs = Caste.objects.all().select_related('religion').order_by('name')
        user = self.request.user
        if user.is_authenticated and getattr(user, 'role', None) == 'admin':
            return qs
        return qs.filter(is_active=True, religion__is_active=True)


class MotherTongueViewSet(viewsets.ModelViewSet):
    serializer_class = MotherTongueSerializer
    permission_classes = [ReadOnlyOrAdmin]
    authentication_classes = []
    filter_backends = [SearchFilter]
    search_fields = ['name']

    def get_queryset(self):
        qs = MotherTongue.objects.all().order_by('name')
        user = self.request.user
        if user.is_authenticated and getattr(user, 'role', None) == 'admin':
            return qs
        return qs.filter(is_active=True)
