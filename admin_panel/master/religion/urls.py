from django.urls import path

from .views import ReligionDetailAPIView, ReligionListCreateAPIView, ReligionToggleStatusAPIView

urlpatterns = [
    path("religions/", ReligionListCreateAPIView.as_view(), name="admin-religion-list-create"),
    path(
        "religions/<int:pk>/toggle-status/",
        ReligionToggleStatusAPIView.as_view(),
        name="admin-religion-toggle-status",
    ),
    path("religions/<int:pk>/", ReligionDetailAPIView.as_view(), name="admin-religion-detail"),
]
