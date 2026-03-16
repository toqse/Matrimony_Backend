from django.db import models
from django.conf import settings
from core.models import SoftDeleteModel


class NotificationLog(SoftDeleteModel):
    CHANNEL_CHOICES = [('email', 'Email'), ('sms', 'SMS')]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_logs',
        null=True,
        blank=True,
    )
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    recipient = models.CharField(max_length=255)
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'notifications_notificationlog'
        ordering = ['-sent_at']
