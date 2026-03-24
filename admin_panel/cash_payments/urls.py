from django.urls import path

from .views import (
    PaymentDetailAPIView,
    PaymentsExportCSVAPIView,
    PaymentsListAPIView,
    PaymentsPDFReportAPIView,
    PaymentsSummaryAPIView,
    RejectPaymentAPIView,
    VerifyPaymentAPIView,
)

urlpatterns = [
    path("", PaymentsListAPIView.as_view(), name="admin-payments-list"),
    path("summary/", PaymentsSummaryAPIView.as_view(), name="admin-payments-summary"),
    path("export/", PaymentsExportCSVAPIView.as_view(), name="admin-payments-export"),
    path("pdf-report/", PaymentsPDFReportAPIView.as_view(), name="admin-payments-pdf-report"),
    path("<int:pk>/", PaymentDetailAPIView.as_view(), name="admin-payments-detail"),
    path("<int:pk>/verify/", VerifyPaymentAPIView.as_view(), name="admin-payments-verify"),
    path("<int:pk>/reject/", RejectPaymentAPIView.as_view(), name="admin-payments-reject"),
]
