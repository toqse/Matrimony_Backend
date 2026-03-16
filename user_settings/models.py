"""
UserSettings: profile visibility, interest request permission, notification preferences.
"""
from django.db import models
from django.conf import settings
from core.models import TimeStampedModel


class UserSettings(TimeStampedModel):
    PROFILE_VISIBILITY_ALL = 'all_users'
    PROFILE_VISIBILITY_PREMIUM = 'premium_only'
    PROFILE_VISIBILITY_HIDDEN = 'hidden'
    PROFILE_VISIBILITY_CHOICES = [
        (PROFILE_VISIBILITY_ALL, 'All users'),
        (PROFILE_VISIBILITY_PREMIUM, 'Premium users only'),
        (PROFILE_VISIBILITY_HIDDEN, 'Hidden'),
    ]
    INTEREST_ALL = 'all_users'
    INTEREST_PREMIUM = 'premium_only'
    INTEREST_PERMISSION_CHOICES = [
        (INTEREST_ALL, 'All users'),
        (INTEREST_PREMIUM, 'Premium users only'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='user_settings',
    )
    profile_visibility = models.CharField(
        max_length=20,
        choices=PROFILE_VISIBILITY_CHOICES,
        default=PROFILE_VISIBILITY_ALL,
    )
    interest_request_permission = models.CharField(
        max_length=20,
        choices=INTEREST_PERMISSION_CHOICES,
        default=INTEREST_ALL,
    )
    notify_interest = models.BooleanField(default=True)
    notify_chat = models.BooleanField(default=True)
    notify_profile_views = models.BooleanField(default=True)
    notify_new_matches = models.BooleanField(default=True)

    class Meta:
        db_table = 'user_settings_usersettings'

    def __str__(self):
        return f'Settings for {self.user.matri_id}'
