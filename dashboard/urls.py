from django.urls import path
from .views import (
    DashboardSummaryView,
    NewMatchesView,
    SuggestionsView,
    TodayPicksView,
)

urlpatterns = [
    path('summary/', DashboardSummaryView.as_view()),
    path('new-matches/', NewMatchesView.as_view()),
    path('suggestions/', SuggestionsView.as_view()),
    path('today-picks/', TodayPicksView.as_view()),
]
