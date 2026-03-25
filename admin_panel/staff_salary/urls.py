from django.urls import path

from .views import (
    StaffSalaryCurrentAPIView,
    StaffSalaryDownloadAPIView,
    StaffSalaryHistoryListAPIView,
    StaffSalarySummaryAPIView,
)

urlpatterns = [
    path("summary/", StaffSalarySummaryAPIView.as_view(), name="staff-salary-summary"),
    path("current/", StaffSalaryCurrentAPIView.as_view(), name="staff-salary-current"),
    path("<int:pk>/download/", StaffSalaryDownloadAPIView.as_view(), name="staff-salary-download"),
    path("", StaffSalaryHistoryListAPIView.as_view(), name="staff-salary-list"),
]
