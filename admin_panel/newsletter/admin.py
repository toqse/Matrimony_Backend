from django.contrib import admin

from .models import NewsletterSubscriber


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "source", "is_active", "subscribed_at")
    list_filter = ("is_active", "source")
    search_fields = ("email",)
    readonly_fields = ("subscribed_at", "updated_at")
