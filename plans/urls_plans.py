"""URLs for user-facing plan list, purchase, and pay remaining service."""
from django.urls import path
from .views import PlanListView, PlanPurchaseView, PayRemainingServiceView
from .views_payments import (
    PlanOrderView,
    PlanVerifyView,
    ServiceChargeOrderView,
    ServiceChargeVerifyView,
)

urlpatterns = [
    path('', PlanListView.as_view()),
    path('order/', PlanOrderView.as_view()),
    path('verify/', PlanVerifyView.as_view()),
    path('purchase/', PlanPurchaseView.as_view()),
    path('pay-remaining-service/order/', ServiceChargeOrderView.as_view()),
    path('pay-remaining-service/verify/', ServiceChargeVerifyView.as_view()),
    path('pay-remaining-service/', PayRemainingServiceView.as_view()),
]
