"""URLs for user-facing plan list, purchase, and pay remaining service."""
from django.urls import path
from .views import PlanListView, PlanPurchaseView, PayRemainingServiceView

urlpatterns = [
    path('', PlanListView.as_view()),
    path('purchase/', PlanPurchaseView.as_view()),
    path('pay-remaining-service/', PayRemainingServiceView.as_view()),
]
