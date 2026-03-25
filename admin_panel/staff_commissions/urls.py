from django.urls import path

from .views import (
    StaffMyCommissionDetailAPIView,
    StaffMyCommissionsExportAPIView,
    StaffMyCommissionsListAPIView,
    StaffMyCommissionsSummaryAPIView,
)

urlpatterns = [
    path("summary/", StaffMyCommissionsSummaryAPIView.as_view(), name="staff-commissions-summary"),
    path("export/", StaffMyCommissionsExportAPIView.as_view(), name="staff-commissions-export"),
    path("<int:pk>/", StaffMyCommissionDetailAPIView.as_view(), name="staff-commission-detail"),
    path("", StaffMyCommissionsListAPIView.as_view(), name="staff-commissions-list"),
]
