from django.urls import path

from .views import (
    DistrictDetailAPIView,
    DistrictListCreateAPIView,
    DistrictStateTabsAPIView,
    DistrictToggleStatusAPIView,
)

urlpatterns = [
    path("districts/states/", DistrictStateTabsAPIView.as_view(), name="admin-district-state-tabs"),
    path("districts/", DistrictListCreateAPIView.as_view(), name="admin-district-list-create"),
    path(
        "districts/<int:pk>/toggle-status/",
        DistrictToggleStatusAPIView.as_view(),
        name="admin-district-toggle-status",
    ),
    path("districts/<int:pk>/", DistrictDetailAPIView.as_view(), name="admin-district-detail"),
]
