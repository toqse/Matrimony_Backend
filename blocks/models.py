from django.db import models
from django.conf import settings

from core.models import TimeStampedModel


class UserBlock(TimeStampedModel):
    """
    Member-to-member block. Distinct from admin User.is_blocked account lock.
    Each row means blocker has blocked blocked.
    """

    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blocks_made',
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blocked_by',
    )

    class Meta:
        db_table = 'blocks_userblock'
        unique_together = (('blocker', 'blocked'),)

    def __str__(self):
        return f'{self.blocker.matri_id} blocked {self.blocked.matri_id}'
