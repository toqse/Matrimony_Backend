from django.urls import path

from .views import CityDetailAPIView, CityDistrictTabsAPIView, CityListCreateAPIView

urlpatterns = [
    path("cities/districts/", CityDistrictTabsAPIView.as_view(), name="admin-city-district-tabs"),
    path("cities/", CityListCreateAPIView.as_view(), name="admin-city-list-create"),
    path("cities/<int:pk>/", CityDetailAPIView.as_view(), name="admin-city-detail"),
]
