from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CountryList, StateList, DistrictList, CityList,
    ReligionList, MotherTongueList, HeightList, MaritalStatusList, IncomeRangeList,
    EducationList, EducationSubjectList, OccupationList,
    ReligionViewSet, CasteViewSet, MotherTongueViewSet,
)

router = DefaultRouter()
router.register('religions', ReligionViewSet, basename='religion')
router.register('castes', CasteViewSet, basename='caste')
router.register('mother-tongues', MotherTongueViewSet, basename='mothertongue')

urlpatterns = [
    path('', include(router.urls)),
    path('countries/', CountryList.as_view()),
    path('states/', StateList.as_view()),
    path('districts/', DistrictList.as_view()),
    path('cities/', CityList.as_view()),
    path('heights/', HeightList.as_view()),
    path('marital-status/', MaritalStatusList.as_view()),
    path('income-ranges/', IncomeRangeList.as_view()),
    path('educations/', EducationList.as_view()),
    path('education-subjects/', EducationSubjectList.as_view()),
    path('occupations/', OccupationList.as_view()),
]
