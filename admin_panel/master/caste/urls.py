from django.urls import path

from .views import CasteDetailAPIView, CasteListCreateAPIView, CasteReligionTabsAPIView, CasteToggleStatusAPIView

urlpatterns = [
    path("castes/religions/", CasteReligionTabsAPIView.as_view(), name="admin-caste-religion-tabs"),
    path("castes/", CasteListCreateAPIView.as_view(), name="admin-caste-list-create"),
    path(
        "castes/<int:pk>/toggle-status/",
        CasteToggleStatusAPIView.as_view(),
        name="admin-caste-toggle-status",
    ),
    path("castes/<int:pk>/", CasteDetailAPIView.as_view(), name="admin-caste-detail"),
]
