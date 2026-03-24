from django.urls import path

from .views import (
    StaffPerformanceChartView,
    StaffPerformanceExportView,
    StaffPerformanceListView,
    StaffPerformanceSummaryView,
    StaffPerformanceTargetsView,
)

urlpatterns = [
    path("summary/", StaffPerformanceSummaryView.as_view(), name="staff-performance-summary"),
    path("chart/", StaffPerformanceChartView.as_view(), name="staff-performance-chart"),
    path("targets/", StaffPerformanceTargetsView.as_view(), name="staff-performance-targets"),
    path("export/", StaffPerformanceExportView.as_view(), name="staff-performance-export"),
    path("", StaffPerformanceListView.as_view(), name="staff-performance-list"),
]
