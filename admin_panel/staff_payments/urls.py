from django.urls import path, re_path

from admin_panel.staff_payments import views

# Receipt IDs are always RCP-YYYY-... (see generate_receipt_no). Using a strict pattern
# avoids reserved paths like "quote/" being captured by <str:receipt_id>/ (POST -> 405).
_RECEIPT = r"^(?P<receipt_id>RCP-\d{4}-[0-9]+)/"

urlpatterns = [
    path("summary/", views.StaffPaymentSummaryView.as_view(), name="staff-payments-summary"),
    path("plans/", views.StaffPaymentPlansListAPIView.as_view(), name="staff-payments-plans"),
    path("quote/", views.StaffPaymentQuoteAPIView.as_view(), name="staff-payments-quote"),
    path(
        "customer-otp/send/",
        views.StaffPaymentCustomerOtpSendAPIView.as_view(),
        name="staff-payments-customer-otp-send",
    ),
    path(
        "customer-otp/verify/",
        views.StaffPaymentCustomerOtpVerifyAPIView.as_view(),
        name="staff-payments-customer-otp-verify",
    ),
    path("customer-lookup/", views.CustomerLookupAPIView.as_view(), name="staff-payments-customer-lookup"),
    re_path(
        _RECEIPT + r"receipt/$",
        views.StaffPaymentReceiptPdfView.as_view(),
        name="staff-payment-receipt-pdf",
    ),
    re_path(
        _RECEIPT + r"verify/$",
        views.BranchPaymentVerifyAPIView.as_view(),
        name="staff-payment-verify",
    ),
    re_path(
        _RECEIPT + r"complete/$",
        views.BranchPaymentCompleteAPIView.as_view(),
        name="staff-payment-complete",
    ),
    re_path(
        _RECEIPT + r"$",
        views.StaffPaymentDetailView.as_view(),
        name="staff-payment-detail",
    ),
    path("", views.StaffPaymentListCreateView.as_view(), name="staff-payments-list"),
]
