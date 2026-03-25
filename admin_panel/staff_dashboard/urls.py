from django.urls import path

from .views import (
    StaffDashboardMyProfileAPIView,
    StaffDashboardRecentActivityAPIView,
    StaffDashboardSummaryAPIView,
)

urlpatterns = [
    path("summary/", StaffDashboardSummaryAPIView.as_view(), name="staff-dashboard-summary"),
    path("me/", StaffDashboardMyProfileAPIView.as_view(), name="staff-dashboard-me"),
    path(
        "recent-activity/",
        StaffDashboardRecentActivityAPIView.as_view(),
        name="staff-dashboard-recent-activity",
    ),
]
