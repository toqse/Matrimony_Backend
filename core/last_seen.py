"""
Update User.last_seen for online presence (chat list, matches, etc.).
"""
from django.utils import timezone
from datetime import timedelta

from accounts.models import User


def touch_user_last_seen(user_pk, *, force=False, min_interval_seconds=90):
    """
    Set last_seen to now for the given user.

    When force=False, skip the DB write if last_seen was updated within
    min_interval_seconds (reduces write load on busy APIs / chat).

    user_pk: UUID or pk of accounts.User
    """
    if not user_pk:
        return
    now = timezone.now()
    if not force:
        last = (
            User.objects.filter(pk=user_pk)
            .values_list('last_seen', flat=True)
            .first()
        )
        if last is not None and (now - last).total_seconds() < min_interval_seconds:
            return
    User.objects.filter(pk=user_pk).update(last_seen=now)


def mark_user_offline(user_pk, *, minutes_ago=16):
    """
    Make the user appear offline immediately.

    Current "online" logic is: online if last_seen is within 15 minutes.
    So we set last_seen to now - 16 minutes (or more).
    """
    if not user_pk:
        return
    offline_ts = timezone.now() - timedelta(minutes=minutes_ago)
    User.objects.filter(pk=user_pk).update(last_seen=offline_ts)
