"""
Celery tasks: OTP (SMS via Twilio/MSG91), email, notifications, profile matching.
"""
from celery import shared_task
from django.conf import settings


@shared_task(bind=True, max_retries=3)
def send_otp_sms(self, phone_number: str, otp: str):
    """Send OTP via SMS using Twilio or MSG91 (from settings)."""
    backend = getattr(settings, 'SMS_BACKEND', 'console')
    success = True
    error_msg = ''
    try:
        if backend == 'twilio':
            from twilio.rest import Client
            account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
            auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
            from_num = getattr(settings, 'TWILIO_PHONE_NUMBER', '')
            if account_sid and auth_token and from_num:
                client = Client(account_sid, auth_token)
                client.messages.create(
                    body=f'Your Aiswarya Matrimony OTP is: {otp}. Valid for 5 minutes.',
                    from_=from_num,
                    to=phone_number,
                )
            else:
                success = False
                error_msg = 'Twilio not configured'
        elif backend == 'msg91':
            import requests
            auth_key = getattr(settings, 'MSG91_AUTH_KEY', '')
            sender = getattr(settings, 'MSG91_SENDER_ID', 'MATRIM')
            if auth_key:
                url = 'https://api.msg91.com/api/v5/flow/'
                payload = {
                    'template_id': getattr(settings, 'MSG91_OTP_TEMPLATE_ID', ''),
                    'short_url': '0',
                    'recipients': [{'mobiles': phone_number.lstrip('+'), 'otp': otp}],
                }
                headers = {'authkey': auth_key, 'Content-Type': 'application/json'}
                r = requests.post(url, json=payload, headers=headers, timeout=10)
                if r.status_code != 200:
                    success = False
                    error_msg = r.text or str(r.status_code)
            else:
                success = False
                error_msg = 'MSG91 not configured'
        else:
            # console / fallback
            print(f'[SMS] OTP for {phone_number}: {otp}')
    except Exception as e:
        success = False
        error_msg = str(e)
        raise self.retry(exc=e, countdown=60)
    try:
        from notifications.models import NotificationLog
        NotificationLog.objects.create(
            channel='sms',
            recipient=phone_number,
            body=f'OTP: {otp}',
            success=success,
            error_message=error_msg,
        )
    except Exception:
        pass
    return success


@shared_task
def send_otp_email(recipient: str, otp: str, subject: str = 'Your OTP'):
    """Send OTP via email."""
    from django.core.mail import send_mail
    success = True
    error_msg = ''
    try:
        send_mail(
            subject=subject,
            message=f'Your OTP is: {otp}. Valid for 5 minutes.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception as e:
        success = False
        error_msg = str(e)
    try:
        from notifications.models import NotificationLog
        NotificationLog.objects.create(
            channel='email',
            recipient=recipient,
            subject=subject,
            body=f'OTP: {otp}',
            success=success,
            error_message=error_msg,
        )
    except Exception:
        pass
    return success


@shared_task
def run_profile_matching(user_id=None):
    """Placeholder: run profile matching algorithm (e.g. daily or on profile update)."""
    # TODO: implement matching logic
    return True
