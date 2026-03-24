from django.urls import path

from .views import BranchSubscriptionsListAPIView

urlpatterns = [
    path("", BranchSubscriptionsListAPIView.as_view(), name="branch-subscriptions-list"),
]
