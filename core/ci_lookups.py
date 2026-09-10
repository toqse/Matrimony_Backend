"""Portable case-insensitive text lookups (MySQL collation-safe)."""
from __future__ import annotations

from django.db.models import CharField, Q, TextField
from django.db.models.functions import Lower

CharField.register_lookup(Lower)
TextField.register_lookup(Lower)


def ci_contains(field: str, value: str) -> Q:
    """Case-insensitive substring match via LOWER(), portable across DB engines."""
    needle = (value or "").casefold()
    if not needle:
        return Q()
    return Q(**{f"{field}__lower__contains": needle})


def ci_exact(field: str, value: str) -> Q:
    """Case-insensitive exact match via LOWER(), portable across DB engines."""
    needle = (value or "").casefold()
    if not needle:
        return Q()
    return Q(**{f"{field}__lower": needle})


def apply_ci_search(qs, search: str, *fields: str):
    """Filter ``qs`` where any of ``fields`` contains ``search`` (case-insensitive)."""
    needle = (search or "").strip()
    if not needle or not fields:
        return qs
    q = Q()
    for field in fields:
        q |= ci_contains(field, needle)
    return qs.filter(q)
