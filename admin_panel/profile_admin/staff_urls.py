from django.urls import path

from .views import StaffProfileListAPIView

urlpatterns = [
    path("", StaffProfileListAPIView.as_view(), name="staff-profiles-list"),
]
