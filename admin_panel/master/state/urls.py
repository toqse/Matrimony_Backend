from django.urls import path

from .views import StateCountryTabsAPIView, StateDetailAPIView, StateListCreateAPIView, StateToggleStatusAPIView

urlpatterns = [
    path("states/countries/", StateCountryTabsAPIView.as_view(), name="admin-state-country-tabs"),
    path("states/", StateListCreateAPIView.as_view(), name="admin-state-list-create"),
    path(
        "states/<int:pk>/toggle-status/",
        StateToggleStatusAPIView.as_view(),
        name="admin-state-toggle-status",
    ),
    path("states/<int:pk>/", StateDetailAPIView.as_view(), name="admin-state-detail"),
]
