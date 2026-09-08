"""Helpers for member-to-member blocks (bidirectional)."""
from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response

from .models import UserBlock

BLOCKED_INTERACTION_MESSAGE = 'You cannot interact with this profile.'


def are_blocked(user_a, user_b) -> bool:
    """True if either user has blocked the other."""
    if not user_a or not user_b:
        return False
    a_id = getattr(user_a, 'pk', None)
    b_id = getattr(user_b, 'pk', None)
    if not a_id or not b_id or a_id == b_id:
        return False
    return UserBlock.objects.filter(
        Q(blocker_id=a_id, blocked_id=b_id) | Q(blocker_id=b_id, blocked_id=a_id)
    ).exists()


def is_blocked_by_me(blocker, other) -> bool:
    """True if blocker has an outgoing block on other."""
    if not blocker or not other:
        return False
    return UserBlock.objects.filter(blocker=blocker, blocked=other).exists()


def blocked_user_ids_for(user):
    """Set of user PKs blocked either way relative to `user`."""
    if not user or not getattr(user, 'pk', None):
        return set()
    outgoing = UserBlock.objects.filter(blocker=user).values_list('blocked_id', flat=True)
    incoming = UserBlock.objects.filter(blocked=user).values_list('blocker_id', flat=True)
    return set(outgoing) | set(incoming)


def exclude_blocked_users(qs, user):
    """Exclude users that have a block relationship with `user` (either direction)."""
    ids = blocked_user_ids_for(user)
    if ids:
        return qs.exclude(pk__in=ids)
    return qs


def blocked_interaction_response():
    return Response(
        {
            'success': False,
            'error': {'code': 403, 'message': BLOCKED_INTERACTION_MESSAGE},
        },
        status=status.HTTP_403_FORBIDDEN,
    )
