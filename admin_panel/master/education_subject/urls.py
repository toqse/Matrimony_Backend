from django.urls import path

from .views import EducationSubjectDetailAPIView, EducationSubjectListCreateAPIView

urlpatterns = [
    path(
        "education-subjects/",
        EducationSubjectListCreateAPIView.as_view(),
        name="admin-education-subject-list-create",
    ),
    path(
        "education-subjects/<int:pk>/",
        EducationSubjectDetailAPIView.as_view(),
        name="admin-education-subject-detail",
    ),
]
