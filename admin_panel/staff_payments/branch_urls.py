from django.urls import path

from admin_panel.staff_payments import views

urlpatterns = [
    path(
        "<str:receipt_id>/verify/",
        views.BranchPaymentVerifyAPIView.as_view(),
        name="branch-payment-verify",
    ),
    path(
        "<str:receipt_id>/complete/",
        views.BranchPaymentCompleteAPIView.as_view(),
        name="branch-payment-complete",
    ),
]

