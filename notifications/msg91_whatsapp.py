"""
MSG91 WhatsApp bulk template client.

Endpoint: POST /api/v5/whatsapp/whatsapp-outbound-message/bulk/
"""
from __future__ import annotations

import logging
from typing import Any

import requests
from admin_panel.msg_config.models import (
    TEMPLATE_OTP,
    TEMPLATE_REGISTRATION_SUCCESS,
    TEMPLATE_SUBSCRIPTION_CONFIRMATION,
    get_msg_config,
    get_msg91_auth_key,
    is_msg_development_mode,
)

logger = logging.getLogger(__name__)

MSG91_WHATSAPP_BULK_URL = (
    "https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/"
)


def normalize_msisdn(mobile: str) -> str:
    """Return digits-only MSISDN with country code, no leading +."""
    digits = "".join(c for c in (mobile or "") if c.isdigit())
    if not digits:
        return ""
    # Common India local 10-digit → prepend 91
    if len(digits) == 10:
        return f"91{digits}"
    return digits


def _log_notification(
    *,
    channel: str,
    recipient: str,
    body: str,
    success: bool,
    error_message: str = "",
    subject: str = "",
) -> None:
    try:
        from notifications.models import NotificationLog

        NotificationLog.objects.create(
            channel=channel,
            recipient=recipient,
            subject=subject,
            body=body,
            success=success,
            error_message=error_message or "",
        )
    except Exception:
        logger.exception("Failed to write NotificationLog")


def _post_template(payload: dict[str, Any], auth_key: str) -> tuple[bool, str]:
    headers = {
        "Content-Type": "application/json",
        "authkey": auth_key,
    }
    try:
        response = requests.post(
            MSG91_WHATSAPP_BULK_URL,
            json=payload,
            headers=headers,
            timeout=15,
        )
        if response.status_code >= 200 and response.status_code < 300:
            return True, ""
        return False, (response.text or str(response.status_code))[:2000]
    except requests.RequestException as exc:
        return False, str(exc)


def _base_payload(
    *,
    template_name: str,
    to: str,
    components: dict[str, Any],
) -> dict[str, Any]:
    config = get_msg_config()
    return {
        "integrated_number": config.resolve_integrated_number(),
        "content_type": "template",
        "payload": {
            "messaging_product": "whatsapp",
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": "en",
                    "policy": "deterministic",
                },
                "namespace": config.resolve_namespace(),
                "to_and_components": [
                    {
                        "to": [to],
                        "components": components,
                    }
                ],
            },
        },
    }


def send_otp_whatsapp(to: str, otp: str) -> bool:
    """Send OTP via WhatsApp template otp_authentication. Skips when development_mode."""
    msisdn = normalize_msisdn(to)
    if not msisdn:
        _log_notification(
            channel="whatsapp",
            recipient=to or "",
            body=f"OTP template skipped: invalid mobile",
            success=False,
            error_message="Invalid mobile",
            subject=TEMPLATE_OTP,
        )
        return False

    if is_msg_development_mode():
        print(f"[OTP] WhatsApp OTP for {msisdn}: {otp}")
        _log_notification(
            channel="whatsapp",
            recipient=msisdn,
            body=f"DEV OTP: {otp}",
            success=True,
            subject=TEMPLATE_OTP,
        )
        return True

    auth_key = get_msg91_auth_key()
    if not auth_key:
        _log_notification(
            channel="whatsapp",
            recipient=msisdn,
            body="OTP send failed: MSG91 auth key not configured",
            success=False,
            error_message="MSG91 auth key not configured",
            subject=TEMPLATE_OTP,
        )
        return False

    otp_str = str(otp)
    payload = _base_payload(
        template_name=TEMPLATE_OTP,
        to=msisdn,
        components={
            "body_1": {"type": "text", "value": otp_str},
            "button_1": {"subtype": "url", "type": "text", "value": otp_str},
        },
    )
    success, error = _post_template(payload, auth_key)
    _log_notification(
        channel="whatsapp",
        recipient=msisdn,
        body=f"OTP sent" if success else f"OTP send failed",
        success=success,
        error_message=error,
        subject=TEMPLATE_OTP,
    )
    return success


def send_registration_success(to: str, customer_name: str) -> bool:
    """Send registration success WhatsApp template. Skips when development_mode."""
    msisdn = normalize_msisdn(to)
    name = (customer_name or "").strip() or "Member"
    if not msisdn:
        return False

    if is_msg_development_mode():
        print(f"[MSG] Skip registration_success for {msisdn} (development_mode)")
        return True

    auth_key = get_msg91_auth_key()
    if not auth_key:
        _log_notification(
            channel="whatsapp",
            recipient=msisdn,
            body="Registration success skipped: MSG91 auth key not configured",
            success=False,
            error_message="MSG91 auth key not configured",
            subject=TEMPLATE_REGISTRATION_SUCCESS,
        )
        return False

    payload = _base_payload(
        template_name=TEMPLATE_REGISTRATION_SUCCESS,
        to=msisdn,
        components={
            "body_customer_name": {
                "type": "text",
                "value": name,
                "parameter_name": "customer_name",
            }
        },
    )
    success, error = _post_template(payload, auth_key)
    _log_notification(
        channel="whatsapp",
        recipient=msisdn,
        body=f"Registration success for {name}",
        success=success,
        error_message=error,
        subject=TEMPLATE_REGISTRATION_SUCCESS,
    )
    return success


def send_subscription_confirmation(
    to: str,
    customer_name: str,
    package_name: str,
    amount,
) -> bool:
    """Send subscription confirmation WhatsApp template. Skips when development_mode."""
    msisdn = normalize_msisdn(to)
    name = (customer_name or "").strip() or "Member"
    package = (package_name or "").strip() or "Plan"
    amount_str = str(amount).strip() if amount is not None else ""
    if not msisdn:
        return False

    if is_msg_development_mode():
        print(
            f"[MSG] Skip subscription_confirmation for {msisdn} "
            f"({package}, {amount_str}) (development_mode)"
        )
        return True

    auth_key = get_msg91_auth_key()
    if not auth_key:
        _log_notification(
            channel="whatsapp",
            recipient=msisdn,
            body="Subscription confirmation skipped: MSG91 auth key not configured",
            success=False,
            error_message="MSG91 auth key not configured",
            subject=TEMPLATE_SUBSCRIPTION_CONFIRMATION,
        )
        return False

    payload = _base_payload(
        template_name=TEMPLATE_SUBSCRIPTION_CONFIRMATION,
        to=msisdn,
        components={
            "body_customer_name": {
                "type": "text",
                "value": name,
                "parameter_name": "customer_name",
            },
            "body_package_name": {
                "type": "text",
                "value": package,
                "parameter_name": "package_name",
            },
            "body_amount": {
                "type": "text",
                "value": amount_str,
                "parameter_name": "amount",
            },
        },
    )
    success, error = _post_template(payload, auth_key)
    _log_notification(
        channel="whatsapp",
        recipient=msisdn,
        body=f"Subscription {package} amount={amount_str} for {name}",
        success=success,
        error_message=error,
        subject=TEMPLATE_SUBSCRIPTION_CONFIRMATION,
    )
    return success
