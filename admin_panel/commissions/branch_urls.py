from django.urls import path

from .views import (
    BranchBulkApproveCommissionAPIView,
    BranchCancelCommissionAPIView,
    BranchCommissionDetailAPIView,
    BranchCommissionSlipAPIView,
    BranchCommissionSummaryAPIView,
    BranchCommissionsListAPIView,
    BranchMarkPaidCommissionAPIView,
    BranchApproveCommissionAPIView,
)

urlpatterns = [
    path("summary/", BranchCommissionSummaryAPIView.as_view(), name="branch-commissions-summary"),
    path("bulk-approve/", BranchBulkApproveCommissionAPIView.as_view(), name="branch-commissions-bulk-approve"),
    path("", BranchCommissionsListAPIView.as_view(), name="branch-commissions-list"),
    path("<int:pk>/", BranchCommissionDetailAPIView.as_view(), name="branch-commissions-detail"),
    path("<int:pk>/approve/", BranchApproveCommissionAPIView.as_view(), name="branch-commissions-approve"),
    path("<int:pk>/mark-paid/", BranchMarkPaidCommissionAPIView.as_view(), name="branch-commissions-mark-paid"),
    path("<int:pk>/cancel/", BranchCancelCommissionAPIView.as_view(), name="branch-commissions-cancel"),
    path("<int:pk>/slip/", BranchCommissionSlipAPIView.as_view(), name="branch-commissions-slip"),
]
