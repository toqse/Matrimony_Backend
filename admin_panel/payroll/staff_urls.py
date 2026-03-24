from django.urls import path

from .views import StaffPayrollListAPIView

urlpatterns = [
    path("", StaffPayrollListAPIView.as_view(), name="staff-payroll-list"),
]
