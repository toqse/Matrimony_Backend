from django.urls import path
from .views import MatchListView, MatchFilterOptionsView

urlpatterns = [
    path('', MatchListView.as_view()),
    path('filters/', MatchFilterOptionsView.as_view()),
]
