from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BranchStaffListAPIView, StaffViewSet

router = DefaultRouter()
router.register(r"", StaffViewSet, basename="admin-staff")

urlpatterns = [
    path("", include(router.urls)),
    path("branch/list/", BranchStaffListAPIView.as_view(), name="branch-staff-list"),
]
