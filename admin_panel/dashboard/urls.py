from django.urls import path

from .views import (
    BranchPerformanceView,
    LeadSourcesView,
    MonthlyRevenueView,
    RecentActivityView,
    SubscriptionGrowthView,
    SummaryView,
)


urlpatterns = [
    path("summary/", SummaryView.as_view()),
    path("monthly-revenue/", MonthlyRevenueView.as_view()),
    path("subscription-growth/", SubscriptionGrowthView.as_view()),
    path("branch-performance/", BranchPerformanceView.as_view()),
    path("lead-sources/", LeadSourcesView.as_view()),
    path("recent-activity/", RecentActivityView.as_view()),
]

