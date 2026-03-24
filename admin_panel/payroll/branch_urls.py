from django.urls import path

from .views import (
    BranchApprovePayrollAPIView,
    BranchGeneratePayrollForbiddenAPIView,
    BranchMarkPaidPayrollForbiddenAPIView,
    BranchPayrollDetailAPIView,
    BranchPayrollDownloadAPIView,
    BranchPayrollListAPIView,
    BranchPayrollSummaryAPIView,
)

urlpatterns = [
    path("summary/", BranchPayrollSummaryAPIView.as_view(), name="branch-payroll-summary"),
    path("generate/", BranchGeneratePayrollForbiddenAPIView.as_view(), name="branch-payroll-generate-forbidden"),
    path("", BranchPayrollListAPIView.as_view(), name="branch-payroll-list"),
    path("<int:pk>/", BranchPayrollDetailAPIView.as_view(), name="branch-payroll-detail"),
    path("<int:pk>/approve/", BranchApprovePayrollAPIView.as_view(), name="branch-payroll-approve"),
    path("<int:pk>/mark-paid/", BranchMarkPaidPayrollForbiddenAPIView.as_view(), name="branch-payroll-mark-paid-forbidden"),
    path("<int:pk>/download/", BranchPayrollDownloadAPIView.as_view(), name="branch-payroll-download"),
]
