"""Time-limited signed URLs for horoscope chart PNG and match PDF (no JWT in browser)."""
from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

_CHART_SALT = 'astrology.horoscope_chart_png'
_REPORT_SALT = 'astrology.match_report_pdf'
_PDF_CREDIT_SALT = 'astrology.jathakam_thalakuri_pdf'


def _max_age() -> int:
    return int(getattr(settings, 'ASTROLOGY_PUBLIC_URL_MAX_AGE', 60 * 60 * 24 * 30))


def sign_chart_access(profile_id: int) -> str:
    return TimestampSigner(salt=_CHART_SALT).sign(str(profile_id))


def verify_chart_access(token: str, profile_id: int) -> bool:
    if not token:
        return False
    try:
        value = TimestampSigner(salt=_CHART_SALT).unsign(token, max_age=_max_age())
        return int(value) == int(profile_id)
    except (BadSignature, SignatureExpired, ValueError):
        return False


def sign_match_report_access(bride_matri_id: str, groom_matri_id: str) -> str:
    payload = f'{bride_matri_id}|{groom_matri_id}'
    return TimestampSigner(salt=_REPORT_SALT).sign(payload)


def verify_match_report_access(token: str, bride_matri_id: str, groom_matri_id: str) -> bool:
    if not token:
        return False
    expected = f'{bride_matri_id}|{groom_matri_id}'
    try:
        value = TimestampSigner(salt=_REPORT_SALT).unsign(token, max_age=_max_age())
        return value == expected
    except (BadSignature, SignatureExpired):
        return False


def sign_pdf_credit_access(credit_id: int) -> str:
    """Signed query token for GET pdf/jathakam/ and pdf/thalakuri/ without JWT (browser-friendly)."""
    return TimestampSigner(salt=_PDF_CREDIT_SALT).sign(str(credit_id))


def verify_pdf_credit_access(token: str, credit_id: int) -> bool:
    if not token:
        return False
    try:
        value = TimestampSigner(salt=_PDF_CREDIT_SALT).unsign(token, max_age=_max_age())
        return int(value) == int(credit_id)
    except (BadSignature, SignatureExpired, ValueError):
        return False
