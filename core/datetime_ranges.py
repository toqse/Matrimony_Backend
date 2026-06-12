"""Timezone-safe datetime range helpers for MySQL date filtering.

Django's ``__date`` lookup generates ``CONVERT_TZ`` SQL which returns NULL
when MySQL timezone tables are not loaded.  These helpers compare against
timezone-aware datetime boundaries instead.
"""
from __future__ import annotations

from datetime import date, datetime, time

from django.utils import timezone


def local_day_start(d: date) -> datetime:
    """Start of a local calendar day as a timezone-aware datetime."""
    return timezone.make_aware(datetime.combine(d, time.min))


def local_day_end(d: date) -> datetime:
    """End of a local calendar day as a timezone-aware datetime."""
    return timezone.make_aware(datetime.combine(d, time.max))


def filter_created_on_date(qs, field: str, d: date):
    """Filter queryset to records created on a local calendar date."""
    return qs.filter(**{
        f'{field}__gte': local_day_start(d),
        f'{field}__lte': local_day_end(d),
    })


def filter_created_in_date_range(qs, field: str, start: date, end_exclusive: date):
    """Filter queryset to records created in [start, end_exclusive) local dates."""
    return qs.filter(**{
        f'{field}__gte': local_day_start(start),
        f'{field}__lt': local_day_start(end_exclusive),
    })
