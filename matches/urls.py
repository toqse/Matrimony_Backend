from django.urls import path
from .views import MatchListView, MatchHomeSliderView, MatchFilterOptionsView

urlpatterns = [
    path('home-slider/', MatchHomeSliderView.as_view()),
    path('', MatchListView.as_view()),
    path('filters/', MatchFilterOptionsView.as_view()),
]
