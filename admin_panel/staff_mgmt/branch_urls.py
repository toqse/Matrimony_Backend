from django.urls import path

from .views import BranchStaffListAPIView

urlpatterns = [
    path("", BranchStaffListAPIView.as_view(), name="branch-staff-list"),
]
