from django.urls import path

from .views import OccupationDetailAPIView, OccupationListCreateAPIView, OccupationToggleStatusAPIView

urlpatterns = [
    path(
        "occupations/",
        OccupationListCreateAPIView.as_view(),
        name="admin-occupation-list-create",
    ),
    path(
        "occupations/<int:pk>/toggle-status/",
        OccupationToggleStatusAPIView.as_view(),
        name="admin-occupation-toggle-status",
    ),
    path(
        "occupations/<int:pk>/",
        OccupationDetailAPIView.as_view(),
        name="admin-occupation-detail",
    ),
]
