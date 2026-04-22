from django.urls import path, re_path

from admin_panel.staff_payments import views

_RECEIPT = r"^(?P<receipt_id>RCP-\d{4}-[0-9]+)/"

urlpatterns = [
    path(
        "customer-lookup/",
        views.CustomerLookupAPIView.as_view(),
        name="branch-payments-customer-lookup",
    ),
    re_path(
        _RECEIPT + r"verify/$",
        views.BranchPaymentVerifyAPIView.as_view(),
        name="branch-payment-verify",
    ),
    re_path(
        _RECEIPT + r"complete/$",
        views.BranchPaymentCompleteAPIView.as_view(),
        name="branch-payment-complete",
    ),
]

