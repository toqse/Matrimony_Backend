from django.urls import path

from .views import CountryDetailAPIView, CountryListCreateAPIView, CountryToggleStatusAPIView

urlpatterns = [
    path("countries/", CountryListCreateAPIView.as_view(), name="admin-country-list-create"),
    path(
        "countries/<int:pk>/toggle-status/",
        CountryToggleStatusAPIView.as_view(),
        name="admin-country-toggle-status",
    ),
    path("countries/<int:pk>/", CountryDetailAPIView.as_view(), name="admin-country-detail"),
]
