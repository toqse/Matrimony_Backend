from django.urls import path

from .views import DistrictAnalysisGeoJSONAPIView, DistrictAnalysisListAPIView

urlpatterns = [
    path("", DistrictAnalysisListAPIView.as_view(), name="admin-district-analysis-list"),
    path("geojson/", DistrictAnalysisGeoJSONAPIView.as_view(), name="admin-district-analysis-geojson"),
]
