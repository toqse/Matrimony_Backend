"""Daily profile rotation — deterministic pseudo-random order per calendar day."""

from django.db.models import CharField, Value
from django.db.models.functions import Cast, Concat, MD5
from django.utils import timezone


def get_daily_rotation_seed(for_date=None) -> str:
    """YYYYMMDD string in project TIME_ZONE (Asia/Kolkata)."""
    day = for_date or timezone.localdate()
    return day.strftime("%Y%m%d")


def annotate_daily_rotation_rank(qs, seed=None):
    """
    Annotate daily_rotation_rank = MD5(pk || seed).

    Same profile id + same calendar day => same rank all day (stable pagination).
    Seed changes at midnight in TIME_ZONE, so ordering rotates automatically.

    Not exposed in API responses; used only for ORDER BY.
    pk tie-breaker applied in order_by() for stable pagination.
    """
    seed = seed if seed is not None else get_daily_rotation_seed()
    return qs.annotate(
        daily_rotation_rank=MD5(
            Concat(
                Cast("pk", output_field=CharField()),
                Value(str(seed)),
                output_field=CharField(),
            )
        )
    )
