from django.db import models
from django.conf import settings

from core.models import TimeStampedModel


class Wishlist(TimeStampedModel):
    """
    Favorite profiles (wishlist) for a user.
    Each row represents one user wishing one other user's profile.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wishlist_items',
    )
    profile = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wishlisted_by',
    )

    class Meta:
        db_table = 'wishlist_wishlist'
        unique_together = (('user', 'profile'),)

    def __str__(self):
        return f'{self.user.matri_id} -> {self.profile.matri_id}'

