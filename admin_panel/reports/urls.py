from django.urls import path

from .views import (
    GrowthReportAPIView,
    PlanPopularityReportAPIView,
    ProductivityReportAPIView,
    ProfileCompletionReportAPIView,
    RevenueReportAPIView,
)

urlpatterns = [
    path("revenue/", RevenueReportAPIView.as_view(), name="admin-reports-revenue"),
    path("productivity/", ProductivityReportAPIView.as_view(), name="admin-reports-productivity"),
    path("growth/", GrowthReportAPIView.as_view(), name="admin-reports-growth"),
    path("profile-completion/", ProfileCompletionReportAPIView.as_view(), name="admin-reports-profile-completion"),
    path("plan-popularity/", PlanPopularityReportAPIView.as_view(), name="admin-reports-plan-popularity"),
]
