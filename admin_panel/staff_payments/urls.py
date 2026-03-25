from django.urls import path

from admin_panel.staff_payments import views

urlpatterns = [
    path("summary/", views.StaffPaymentSummaryView.as_view(), name="staff-payments-summary"),
    path(
        "<str:receipt_id>/receipt/",
        views.StaffPaymentReceiptPdfView.as_view(),
        name="staff-payment-receipt-pdf",
    ),
    path(
        "<str:receipt_id>/verify/",
        views.BranchPaymentVerifyAPIView.as_view(),
        name="staff-payment-verify",
    ),
    path(
        "<str:receipt_id>/complete/",
        views.BranchPaymentCompleteAPIView.as_view(),
        name="staff-payment-complete",
    ),
    path("<str:receipt_id>/", views.StaffPaymentDetailView.as_view(), name="staff-payment-detail"),
    path("", views.StaffPaymentListCreateView.as_view(), name="staff-payments-list"),
]
