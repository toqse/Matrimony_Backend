from django.urls import path
from .views import (
    SendInterestView,
    MyInterestsView,
    SentInterestsView,
    ReceivedInterestsView,
    RespondInterestView,
    CancelInterestView,
)

urlpatterns = [
    path('send/', SendInterestView.as_view()),
    path('my/', MyInterestsView.as_view()),
    path('sent/', SentInterestsView.as_view()),
    path('received/', ReceivedInterestsView.as_view()),
    path('respond/', RespondInterestView.as_view()),
    path('cancel/', CancelInterestView.as_view()),
]
