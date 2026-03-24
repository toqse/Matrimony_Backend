from django.urls import path

from .views import MotherTongueDetailAPIView, MotherTongueListCreateAPIView

urlpatterns = [
    path("mother-tongues/", MotherTongueListCreateAPIView.as_view(), name="admin-mother-tongue-list-create"),
    path("mother-tongues/<int:pk>/", MotherTongueDetailAPIView.as_view(), name="admin-mother-tongue-detail"),
]
