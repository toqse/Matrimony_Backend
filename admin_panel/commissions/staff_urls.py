from django.urls import path

from .views import StaffCommissionsListAPIView

urlpatterns = [
    path("", StaffCommissionsListAPIView.as_view(), name="staff-commissions-list"),
]
