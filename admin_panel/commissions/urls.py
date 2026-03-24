from django.urls import path

from .views import (
    AdminCommissionsListAPIView,
    ApproveCommissionAPIView,
    BulkApproveCommissionAPIView,
    CancelCommissionAPIView,
    CommissionDetailAPIView,
    CommissionSlipAPIView,
    MarkPaidCommissionAPIView,
)

urlpatterns = [
    path("", AdminCommissionsListAPIView.as_view(), name="admin-commissions-list"),
    path("bulk-approve/", BulkApproveCommissionAPIView.as_view(), name="admin-commissions-bulk-approve"),
    path("<int:pk>/", CommissionDetailAPIView.as_view(), name="admin-commissions-detail"),
    path("<int:pk>/approve/", ApproveCommissionAPIView.as_view(), name="admin-commissions-approve"),
    path("<int:pk>/mark-paid/", MarkPaidCommissionAPIView.as_view(), name="admin-commissions-mark-paid"),
    path("<int:pk>/cancel/", CancelCommissionAPIView.as_view(), name="admin-commissions-cancel"),
    path("<int:pk>/slip/", CommissionSlipAPIView.as_view(), name="admin-commissions-slip"),
]
