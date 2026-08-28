from django.urls import path

from .views import EducationDetailAPIView, EducationListCreateAPIView, EducationToggleStatusAPIView

urlpatterns = [
    path(
        "educations/",
        EducationListCreateAPIView.as_view(),
        name="admin-education-list-create",
    ),
    path(
        "educations/<int:pk>/toggle-status/",
        EducationToggleStatusAPIView.as_view(),
        name="admin-education-toggle-status",
    ),
    path(
        "educations/<int:pk>/",
        EducationDetailAPIView.as_view(),
        name="admin-education-detail",
    ),
]
