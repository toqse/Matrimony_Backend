from django.urls import path

from .views import (
    ApprovePayrollAPIView,
    GeneratePayrollAPIView,
    MarkPaidPayrollAPIView,
    PayrollDetailAPIView,
    PayrollDownloadAPIView,
    PayrollListAPIView,
    PayrollSummaryAPIView,
)

urlpatterns = [
    path("", PayrollListAPIView.as_view(), name="admin-payroll-list"),
    path("generate/", GeneratePayrollAPIView.as_view(), name="admin-payroll-generate"),
    path("summary/", PayrollSummaryAPIView.as_view(), name="admin-payroll-summary"),
    path("<int:pk>/", PayrollDetailAPIView.as_view(), name="admin-payroll-detail"),
    path("<int:pk>/approve/", ApprovePayrollAPIView.as_view(), name="admin-payroll-approve"),
    path("<int:pk>/mark-paid/", MarkPaidPayrollAPIView.as_view(), name="admin-payroll-mark-paid"),
    path("<int:pk>/download/", PayrollDownloadAPIView.as_view(), name="admin-payroll-download"),
]
