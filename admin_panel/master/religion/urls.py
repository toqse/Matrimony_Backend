from django.urls import path

from .views import ReligionDetailAPIView, ReligionListCreateAPIView

urlpatterns = [
    path("religions/", ReligionListCreateAPIView.as_view(), name="admin-religion-list-create"),
    path("religions/<int:pk>/", ReligionDetailAPIView.as_view(), name="admin-religion-detail"),
]
