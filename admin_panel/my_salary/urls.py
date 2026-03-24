from django.urls import path

from .views import (
    MySalaryCurrentView,
    MySalaryDownloadView,
    MySalaryListView,
    MySalarySummaryView,
)

urlpatterns = [
    path("summary/", MySalarySummaryView.as_view(), name="my-salary-summary"),
    path("current/", MySalaryCurrentView.as_view(), name="my-salary-current"),
    path("<int:pk>/download/", MySalaryDownloadView.as_view(), name="my-salary-download"),
    path("", MySalaryListView.as_view(), name="my-salary-list"),
]
