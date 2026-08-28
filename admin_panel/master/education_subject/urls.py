from django.urls import path

from .views import (
    EducationSubjectDetailAPIView,
    EducationSubjectListCreateAPIView,
    EducationSubjectToggleStatusAPIView,
)

urlpatterns = [
    path(
        "education-subjects/",
        EducationSubjectListCreateAPIView.as_view(),
        name="admin-education-subject-list-create",
    ),
    path(
        "education-subjects/<int:pk>/toggle-status/",
        EducationSubjectToggleStatusAPIView.as_view(),
        name="admin-education-subject-toggle-status",
    ),
    path(
        "education-subjects/<int:pk>/",
        EducationSubjectDetailAPIView.as_view(),
        name="admin-education-subject-detail",
    ),
]
