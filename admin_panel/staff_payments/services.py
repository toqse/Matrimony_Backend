from __future__ import annotations

import hashlib
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import OTPRecord
from django.core.cache import cache

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


def generate_receipt_no() -> str:
    """Public helper for payment flows."""
    return allocate_next_receipt_id()


def _otp_cache_key(identifier: str) -> str:
    return f"otp:{identifier}"


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def validate_otp(*, phone_number: str, otp: str) -> tuple[bool, str]:
    """
    Validate OTP against existing OTP store (cache + OTPRecord) with stricter
    payment guardrails: 5-minute expiry and max 3 attempts.
    """
    if not phone_number or not otp:
        return False, "OTP is required."
    identifier = f"phone:{phone_number}"
    attempt_limit = 3
    expiry_minutes = max(5, min(getattr(settings, "OTP_EXPIRY_MINUTES", 5), 10))

    payload = cache.get(_otp_cache_key(identifier))
    rec = OTPRecord.objects.filter(identifier=identifier).order_by("-created_at").first()

    current_attempts = 0
    if payload and isinstance(payload, dict):
        current_attempts = int(payload.get("attempts", 0) or 0)
    elif rec:
        current_attempts = int(rec.attempts or 0)
    if current_attempts >= attempt_limit:
        return False, "Too many OTP attempts. Please request a new OTP."

    if payload and payload.get("expires_at"):
        try:
            exp = datetime.fromisoformat(str(payload["expires_at"]).replace("Z", "+00:00"))
            if timezone.now() > exp:
                return False, "OTP expired."
        except Exception:
            pass
    elif rec and rec.expires_at and timezone.now() > rec.expires_at:
        return False, "OTP expired."
    elif rec and (timezone.now() - rec.created_at).total_seconds() > (expiry_minutes * 60):
        return False, "OTP expired."

    from accounts.services import verify_otp  # existing OTP verification flow

    ok, msg = verify_otp(identifier, otp)
    if not ok:
        if "too many" in (msg or "").lower():
            return False, "Too many OTP attempts. Please request a new OTP."
        if "expired" in (msg or "").lower():
            return False, "OTP expired."
        return False, "Invalid OTP. Please try again."
    return True, "OK"
