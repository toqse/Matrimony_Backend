from django.urls import path

from .views import EducationDetailAPIView, EducationListCreateAPIView

urlpatterns = [
    path(
        "educations/",
        EducationListCreateAPIView.as_view(),
        name="admin-education-list-create",
    ),
    path(
        "educations/<int:pk>/",
        EducationDetailAPIView.as_view(),
        name="admin-education-detail",
    ),
]
