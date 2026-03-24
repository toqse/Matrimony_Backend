from django.core.exceptions import ValidationError
from django.db import models

from admin_panel.auth.models import AdminUser
from core.models import TimeStampedModel


class AuditLog(TimeStampedModel):
    ACTION_PROFILE_VERIFY = "profile_verify"
    ACTION_PROFILE_UNVERIFY = "profile_unverify"
    ACTION_COMMISSION_CREATE = "commission_create"
    ACTION_COMMISSION_UPDATE = "commission_update"
    ACTION_BRANCH_UPDATE = "branch_update"
    ACTION_STAFF_UPDATE = "staff_update"
    ACTION_SUBSCRIPTION_UPDATE = "subscription_update"
    ACTION_OTHER = "other"

    ACTION_CHOICES = (
        (ACTION_PROFILE_VERIFY, "Profile Verified"),
        (ACTION_PROFILE_UNVERIFY, "Profile Unverified"),
        (ACTION_COMMISSION_CREATE, "Commission Created"),
        (ACTION_COMMISSION_UPDATE, "Commission Updated"),
        (ACTION_BRANCH_UPDATE, "Branch Updated"),
        (ACTION_STAFF_UPDATE, "Staff Updated"),
        (ACTION_SUBSCRIPTION_UPDATE, "Subscription Updated"),
        (ACTION_OTHER, "Other"),
    )

    actor = models.ForeignKey(
        AdminUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor_name = models.CharField(max_length=150, blank=True)
    actor_role = models.CharField(max_length=20, blank=True)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    resource = models.CharField(max_length=255)
    details = models.TextField(blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "admin_audit_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["action"]),
            models.Index(fields=["actor_role"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("AuditLog records are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("AuditLog records are immutable.")
