"""Helpers to enqueue MSG91 WhatsApp template notifications."""


def enqueue_registration_success(user) -> None:
    mobile = (getattr(user, "mobile", None) or "").strip()
    if not mobile:
        return
    name = (getattr(user, "name", None) or "").strip() or "Member"
    try:
        from notifications.tasks import send_registration_success_whatsapp_task

        send_registration_success_whatsapp_task.delay(mobile, name)
    except Exception:
        try:
            from notifications.msg91_whatsapp import send_registration_success

            send_registration_success(mobile, name)
        except Exception:
            pass


def enqueue_subscription_confirmation(user, plan, amount) -> None:
    mobile = (getattr(user, "mobile", None) or "").strip()
    if not mobile:
        return
    name = (getattr(user, "name", None) or "").strip() or "Member"
    package_name = (getattr(plan, "name", None) or "").strip() or "Plan"
    amount_str = str(amount).strip() if amount is not None else ""
    try:
        from notifications.tasks import send_subscription_confirmation_whatsapp_task

        send_subscription_confirmation_whatsapp_task.delay(
            mobile, name, package_name, amount_str
        )
    except Exception:
        try:
            from notifications.msg91_whatsapp import send_subscription_confirmation

            send_subscription_confirmation(mobile, name, package_name, amount_str)
        except Exception:
            pass
