"""
Auth services: OTP generate/verify (Redis + DB fallback), rate limit, password reset.
"""
import hashlib
import secrets
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache


def _otp_key(identifier):
    return f'otp:{identifier}'


def _otp_rate_limit_key(identifier):
    return f'otp_rate:{identifier}'


def _pending_register_key(phone_e164: str) -> str:
    return f'pending_register:{phone_e164}'


def set_pending_registration(phone_e164: str, payload: dict) -> None:
    """
    Store registration fields until OTP is verified. TTL matches OTP expiry.
    """
    expiry_minutes = getattr(settings, 'OTP_EXPIRY_MINUTES', 5)
    cache.set(
        _pending_register_key(phone_e164),
        payload,
        timeout=max(60, expiry_minutes * 60 + 30),
    )


def get_pending_registration(phone_e164: str) -> dict | None:
    return cache.get(_pending_register_key(phone_e164))


def pop_pending_registration(phone_e164: str) -> dict | None:
    key = _pending_register_key(phone_e164)
    data = cache.get(key)
    if data is not None:
        cache.delete(key)
    return data


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def check_otp_rate_limit(identifier: str) -> tuple[bool, str]:
    """
    Rate limit: max OTP_REQUESTS per WINDOW minutes per identifier.
    Returns (True, '') if allowed, (False, message) if rate limited.
    """
    max_requests = getattr(settings, 'OTP_RATE_LIMIT_REQUESTS', 5)
    window_minutes = getattr(settings, 'OTP_RATE_LIMIT_WINDOW_MINUTES', 10)
    key = _otp_rate_limit_key(identifier)
    data = cache.get(key) or {'count': 0, 'start': timezone.now().isoformat()}
    count = data.get('count', 0)
    from datetime import datetime
    start = datetime.fromisoformat(data['start'].replace('Z', '+00:00'))
    if timezone.now() > start + timezone.timedelta(minutes=window_minutes):
        count = 0
        start = timezone.now()
        data = {'count': 0, 'start': start.isoformat()}
    if count >= max_requests:
        return False, f'Too many OTP requests. Try again after {window_minutes} minutes.'
    data['count'] = count + 1
    data['start'] = data.get('start', start.isoformat())
    cache.set(key, data, timeout=window_minutes * 60)
    return True, ''


def generate_otp(identifier: str, length: int = None) -> str:
    length = length or getattr(settings, 'OTP_LENGTH', 6)
    otp = ''.join(secrets.choice('0123456789') for _ in range(length))
    expiry_minutes = getattr(settings, 'OTP_EXPIRY_MINUTES', 5)
    expires_at = timezone.now() + timezone.timedelta(minutes=expiry_minutes)
    payload = {
        'otp_hash': _hash_otp(otp),
        'attempts': 0,
        'expires_at': expires_at.isoformat(),
    }
    cache_key = _otp_key(identifier)
    cache.set(cache_key, payload, timeout=expiry_minutes * 60)
    try:
        from accounts.models import OTPRecord
        OTPRecord.objects.filter(identifier=identifier).delete()
        OTPRecord.objects.create(
            identifier=identifier,
            otp_hash=payload['otp_hash'],
            expires_at=expires_at,
        )
    except Exception:
        pass
    return otp


def verify_otp(identifier: str, otp: str) -> tuple[bool, str]:
    attempt_limit = getattr(settings, 'OTP_ATTEMPT_LIMIT', 5)
    cache_key = _otp_key(identifier)
    payload = cache.get(cache_key)
    if payload is None:
        try:
            from accounts.models import OTPRecord
            rec = OTPRecord.objects.filter(identifier=identifier).order_by('-created_at').first()
            if not rec or rec.verified:
                return False, 'OTP expired or invalid.'
            if rec.attempts >= attempt_limit:
                return False, 'Too many attempts.'
            if timezone.now() > rec.expires_at:
                return False, 'OTP expired.'
            payload = {'otp_hash': rec.otp_hash, 'attempts': rec.attempts}
        except Exception:
            return False, 'OTP expired or invalid.'
    else:
        try:
            from accounts.models import OTPRecord
            rec = OTPRecord.objects.filter(identifier=identifier).order_by('-created_at').first()
            if rec and rec.attempts >= attempt_limit:
                cache.delete(cache_key)
                return False, 'Too many attempts.'
        except Exception:
            pass

    attempts = payload.get('attempts', 0)
    if attempts >= attempt_limit:
        cache.delete(cache_key)
        return False, 'Too many attempts.'

    expires_at = payload.get('expires_at')
    if expires_at:
        from datetime import datetime
        exp = datetime.fromisoformat(expires_at.replace('Z', '+00:00')) if isinstance(expires_at, str) else expires_at
        if timezone.now() > exp:
            cache.delete(cache_key)
            return False, 'OTP expired.'

    if payload.get('otp_hash') != _hash_otp(otp):
        attempts += 1
        if 'expires_at' in payload:
            cache.set(cache_key, {**payload, 'attempts': attempts}, timeout=300)
        try:
            from accounts.models import OTPRecord
            OTPRecord.objects.filter(identifier=identifier).update(attempts=attempts)
        except Exception:
            pass
        return False, 'Invalid OTP.'

    cache.delete(cache_key)
    try:
        from accounts.models import OTPRecord
        OTPRecord.objects.filter(identifier=identifier).update(verified=True)
    except Exception:
        pass
    return True, 'OK'
