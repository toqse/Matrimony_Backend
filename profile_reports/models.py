from django.db import models
from django.conf import settings

from core.models import TimeStampedModel


class ProfileReport(TimeStampedModel):
    """Member report of another profile (abuse / safety), for admin review."""

    STATUS_PENDING = 'pending'
    STATUS_REVIEWED = 'reviewed'
    STATUS_DISMISSED = 'dismissed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_REVIEWED, 'Reviewed'),
        (STATUS_DISMISSED, 'Dismissed'),
    ]

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reports_made',
    )
    reported = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reports_received',
    )
    message = models.TextField(max_length=2000)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    class Meta:
        db_table = 'profile_reports_profilereport'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reporter.matri_id} → {self.reported.matri_id} ({self.status})'
