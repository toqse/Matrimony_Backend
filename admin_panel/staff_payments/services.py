from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import PaymentReceiptSequence


def allocate_next_receipt_id() -> str:
    """Format RCP-{YYYY}-{NNN} with per-year sequence; 4+ digits if NNN overflows 999."""
    year = timezone.now().year
    with transaction.atomic():
        row, _ = PaymentReceiptSequence.objects.select_for_update().get_or_create(
            year=year,
            defaults={"last_number": 0},
        )
        row.last_number += 1
        row.save(update_fields=["last_number"])
        n = row.last_number
    suffix = f"{n:03d}" if n <= 999 else str(n)
    return f"RCP-{year}-{suffix}"
