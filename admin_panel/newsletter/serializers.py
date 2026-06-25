from rest_framework import serializers

from .models import NewsletterSubscriber


class NewsletterSubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscriber
        fields = ("id", "email", "source", "is_active", "subscribed_at", "updated_at")
