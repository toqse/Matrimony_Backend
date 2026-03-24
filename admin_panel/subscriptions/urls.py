from django.urls import path

from .views import (
    AdminSubscriptionsListAPIView,
    SubscriptionDetailAPIView,
    SubscriptionsExportCSVAPIView,
)

urlpatterns = [
    path("", AdminSubscriptionsListAPIView.as_view(), name="admin-subscriptions-list"),
    path("export/", SubscriptionsExportCSVAPIView.as_view(), name="admin-subscriptions-export"),
    path("<int:pk>/", SubscriptionDetailAPIView.as_view(), name="admin-subscriptions-detail"),
]
