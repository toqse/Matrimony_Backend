from django.urls import path

from .views import OccupationDetailAPIView, OccupationListCreateAPIView

urlpatterns = [
    path(
        "occupations/",
        OccupationListCreateAPIView.as_view(),
        name="admin-occupation-list-create",
    ),
    path(
        "occupations/<int:pk>/",
        OccupationDetailAPIView.as_view(),
        name="admin-occupation-detail",
    ),
]
