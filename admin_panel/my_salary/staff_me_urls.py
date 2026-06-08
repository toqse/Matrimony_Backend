from django.urls import path

from .views import (
    MySalaryCurrentView,
    MySalaryDownloadView,
    MySalaryListView,
    MySalarySummaryView,
)

urlpatterns = [
    path("summary/", MySalarySummaryView.as_view(), name="staff-me-salary-summary"),
    path("current/", MySalaryCurrentView.as_view(), name="staff-me-salary-current"),
    path("<int:pk>/download/", MySalaryDownloadView.as_view(), name="staff-me-salary-download"),
    path("", MySalaryListView.as_view(), name="staff-me-salary-list"),
]
