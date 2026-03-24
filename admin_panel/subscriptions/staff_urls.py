from django.urls import path

from .views import StaffSubscriptionsListAPIView

urlpatterns = [
    path("", StaffSubscriptionsListAPIView.as_view(), name="staff-subscriptions-list"),
]
