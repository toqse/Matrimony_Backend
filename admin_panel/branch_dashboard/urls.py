from django.urls import path

from .views import (
    BranchDashboardSummaryView,
    BranchEnquiryOverviewView,
    BranchRevenueTrendView,
    BranchStaffPerformanceView,
    BranchTargetProgressView,
    BranchTopPerformersView,
)

urlpatterns = [
    path("summary/", BranchDashboardSummaryView.as_view(), name="branch-dashboard-summary"),
    path("revenue-trend/", BranchRevenueTrendView.as_view(), name="branch-dashboard-revenue-trend"),
    path("staff-performance/", BranchStaffPerformanceView.as_view(), name="branch-dashboard-staff-performance"),
    path("target-progress/", BranchTargetProgressView.as_view(), name="branch-dashboard-target-progress"),
    path("top-performers/", BranchTopPerformersView.as_view(), name="branch-dashboard-top-performers"),
    path("enquiry-overview/", BranchEnquiryOverviewView.as_view(), name="branch-dashboard-enquiry-overview"),
]
