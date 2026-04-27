"""Normalize father/mother status (Alive / Late) for API and bulk upload."""

PARENT_STATUS_ALIVE = "Alive"
PARENT_STATUS_LATE = "Late"
PARENT_STATUS_VALUES = frozenset((PARENT_STATUS_ALIVE, PARENT_STATUS_LATE))


def normalize_parent_status(value):
    """
    Return '' if empty; 'Alive' or 'Late' if valid; None if a non-empty value is invalid.
    Accepts case-insensitive alive/late and exact Alive/Late.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    low = s.lower()
    if low == "alive":
        return PARENT_STATUS_ALIVE
    if low == "late":
        return PARENT_STATUS_LATE
    if s in PARENT_STATUS_VALUES:
        return s
    return None
