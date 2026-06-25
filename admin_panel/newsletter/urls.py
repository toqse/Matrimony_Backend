from django.urls import path

from .views import NewsletterSubscriberListAPIView

urlpatterns = [
    path("", NewsletterSubscriberListAPIView.as_view(), name="admin-newsletter-subscribers"),
]
