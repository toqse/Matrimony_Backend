"""
Auth views: register (mobile/email), verify, login, refresh, logout, password reset/confirm.
New flow: register (name, phone, email, dob, gender) -> verify-otp -> tokens.
"""
from django.conf import settings
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.utils import timezone
from core.last_seen import mark_user_offline
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from .serializers import (
    RegisterSerializer,
    ResendOTPSerializer,
    VerifyOTPSerializer,
    get_verify_otp_response_data,
    RegisterMobileSerializer,
    VerifyMobileSerializer,
    RegisterEmailSerializer,
    VerifyEmailSerializer,
    LoginSerializer,
    PasswordResetSerializer,
    PasswordConfirmSerializer,
    get_user_by_mobile_variants,
)
from .services import (
    generate_otp,
    verify_otp,
    check_otp_rate_limit,
    check_resend_otp_rate_limit,
    set_pending_registration,
)
from .models import User
from admin_panel.audit_log.utils import create_audit_log


def _send_otp_mobile(mobile: str, otp: str):
    # Prefer Celery task; fallback to sync
    try:
        from notifications.tasks import send_otp_sms
        send_otp_sms.delay(mobile, otp)
    except Exception:
        print(f'[SMS] OTP for {mobile}: {otp}')
    return True


def _send_otp_email(email: str, otp: str):
    from django.core.mail import send_mail
    from django.conf import settings
    send_mail(
        subject='Your OTP',
        message=f'Your OTP is: {otp}. Valid for 5 minutes.',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=True,
    )
    return True


def _tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {'access': str(refresh.access_token), 'refresh': str(refresh)}


def _set_refresh_cookie(response, refresh_token):
    cookie_name = getattr(settings, 'JWT_REFRESH_COOKIE_NAME', 'refresh_token')
    httponly = getattr(settings, 'JWT_REFRESH_COOKIE_HTTPONLY', True)
    secure = getattr(settings, 'JWT_REFRESH_COOKIE_SECURE', False)
    samesite = getattr(settings, 'JWT_REFRESH_COOKIE_SAMESITE', 'Lax')
    max_age = 30 * 24 * 60 * 60  # 30 days
    response.set_cookie(
        cookie_name,
        refresh_token,
        max_age=max_age,
        httponly=httponly,
        secure=secure,
        samesite=samesite,
    )


# --- New registration flow ---

class RegisterView(APIView):
    """
    POST /api/v1/auth/register/
    Body: name, phone_number, dob, gender. (email is optional)
    Stores registration data until OTP is verified; sends OTP. No user row is created until
    POST /api/v1/auth/verify-otp/ succeeds. Returns phone_number (matri_id only after verify).
    """
    permission_classes = [AllowAny]

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        phone = data['phone_number']
        identifier = f'phone:{phone}'
        allowed, msg = check_otp_rate_limit(identifier)
        if not allowed:
            return Response({
                'success': False,
                'error': {'code': 429, 'message': msg},
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
        existing_verified = get_user_by_mobile_variants(phone)
        if existing_verified and existing_verified.mobile_verified:
            return Response({
                'success': False,
                'error': {'code': 400, 'message': 'Phone number already registered'},
            }, status=status.HTTP_400_BAD_REQUEST)
        # Remove incomplete registrations so the DB has no account until OTP verification.
        for mobile_val in {phone, f"91{phone[-10:]}", phone[-10:]}:
            User.objects.filter(mobile=mobile_val, mobile_verified=False).delete()
        profile_for = data.get('profile_for') or None
        email = data.get('email') or None
        set_pending_registration(
            phone,
            {
                'name': data['name'],
                'email': email,
                'dob': data['dob'].isoformat(),
                'gender': data['gender'],
                'profile_for': profile_for,
            },
        )
        otp = generate_otp(identifier)
        _send_otp_mobile(phone, otp)
        payload = {
            'success': True,
            'message': 'OTP has been sent to your phone number. Verify to create your account.',
            'data': {
                'phone_number': phone,
                'otp_sent': True,
                'registration_pending': True,
            },
        }
        # Expose OTP only in development/testing to simplify QA.
        if getattr(settings, 'DEBUG', False):
            payload['data']['otp'] = otp
        return Response(payload, status=status.HTTP_200_OK)


class ResendOTPView(APIView):
    """
    POST /api/v1/auth/resend-otp/
    Body: phone_number (E164). Sends a new OTP (rate-limited). Identifier:
      - mobile_verified user -> mobile:{phone} (login / verify-mobile / login)
      - otherwise -> phone:{phone} (signup / verify-otp), including cold resend when Redis
        pending data was lost or user has not called register/ yet.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        ser = ResendOTPSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        phone = ser.validated_data["phone_number"]

        user = get_user_by_mobile_variants(phone)
        if user and not user.mobile_verified:
            user = None

        allowed, msg = check_resend_otp_rate_limit(phone)
        if not allowed:
            return Response(
                {
                    "success": False,
                    "error": {"code": 429, "message": msg},
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Verified member: same key as register/mobile/ + login.
        # Not verified (pending or no row / lost cache): same key as register/ + verify-otp.
        identifier = f"mobile:{phone}" if user else f"phone:{phone}"
        otp = generate_otp(identifier)
        _send_otp_mobile(phone, otp)

        payload = {
            "success": True,
            "message": "OTP has been sent to your phone number.",
            "data": {
                "phone_number": phone,
                "otp_sent": True,
            },
        }
        if getattr(settings, "DEBUG", False):
            payload["data"]["otp"] = otp
        return Response(payload, status=status.HTTP_200_OK)


class VerifyOTPView(APIView):
    """
    POST /api/v1/auth/verify-otp/
    Body: phone_number, otp.
    Returns: access_token, refresh_token (and in cookie if configured), matri_id,
             is_registered, is_registration_profile_completed, profile_status,
             profile_steps, profile_completion_percentage, next_step.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        ser = VerifyOTPSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.validated_data['user']
        if getattr(user, 'is_blocked', False):
            return Response({
                'success': False,
                'error': {'code': 403, 'message': 'Your account has been blocked.'},
            }, status=status.HTTP_403_FORBIDDEN)
        if not user.mobile_verified:
            user.mobile_verified = True
            user.is_active = True
            user.save(update_fields=['mobile_verified', 'is_active', 'updated_at'])
        tokens = _tokens_for_user(user)
        response = Response({
            'success': True,
            'data': get_verify_otp_response_data(user, tokens, request=request),
        }, status=status.HTTP_200_OK)
        if getattr(settings, 'JWT_REFRESH_COOKIE_NAME', None):
            _set_refresh_cookie(response, tokens['refresh'])
        create_audit_log(
            request,
            action='otp_verify',
            resource=f'user:{user.id}',
            details='User OTP verified successfully.',
        )
        return response


class RegisterMobileView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ser = RegisterMobileSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        mobile = ser.validated_data['mobile']
        user = get_user_by_mobile_variants(mobile)
        if user and not user.mobile_verified:
            user = None
        if not user:
            return Response({
                'success': False,
                'error': {'code': 404, 'message': 'No registered account found with this mobile number. Please register first.'},
            }, status=status.HTTP_404_NOT_FOUND)
        identifier = f'mobile:{mobile}'
        otp = generate_otp(identifier)
        _send_otp_mobile(mobile, otp)
        payload = {
            'success': True,
            'message': 'OTP sent to mobile',
            'data': {'mobile': mobile},
        }
        # Expose OTP in development/testing only.
        if getattr(settings, 'DEBUG', False):
            payload['data']['otp'] = otp
        return Response(payload, status=status.HTTP_200_OK)


class VerifyMobileView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ser = VerifyMobileSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        mobile = ser.validated_data['mobile']
        otp = ser.validated_data['otp']
        # OTP may have been sent from register (phone:) or register/mobile (mobile:); try both
        ok, msg = False, 'OTP expired or invalid.'
        for prefix in ('phone:', 'mobile:'):
            identifier = f'{prefix}{mobile}'
            ok, msg = verify_otp(identifier, otp)
            if ok:
                break
        if not ok:
            return Response({
                'success': False,
                'error': {'message': msg},
            }, status=status.HTTP_400_BAD_REQUEST)
        # Bulk upload may store mobile as 10 digits (or other variants). Avoid creating
        # a duplicate empty user row by reusing any existing variant.
        user = get_user_by_mobile_variants(mobile)
        if not user:
            user = User.objects.create_user(
                mobile=mobile,
                password=User.objects.make_random_password(),
                is_active=True,
                mobile_verified=True,
            )
        elif not user.mobile_verified or not user.is_active:
            user.mobile_verified = True
            user.is_active = True
            user.save(update_fields=['mobile_verified', 'is_active', 'updated_at'])
        tokens = _tokens_for_user(user)
        response = Response({
            'success': True,
            'data': get_verify_otp_response_data(user, tokens, request=request),
        }, status=status.HTTP_200_OK)
        if getattr(settings, 'JWT_REFRESH_COOKIE_NAME', None):
            _set_refresh_cookie(response, tokens['refresh'])
        return response


class RegisterEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ser = RegisterEmailSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = ser.validated_data['email']
        identifier = f'email:{email}'
        otp = generate_otp(identifier)
        _send_otp_email(email, otp)
        return Response({
            'success': True,
            'message': 'OTP sent to email',
            'data': {'email': email},
        }, status=status.HTTP_200_OK)


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ser = VerifyEmailSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = ser.validated_data['email']
        otp = ser.validated_data['otp']
        identifier = f'email:{email}'
        ok, msg = verify_otp(identifier, otp)
        if not ok:
            return Response({
                'success': False,
                'error': {'message': msg},
            }, status=status.HTTP_400_BAD_REQUEST)
        user, created = User.objects.get_or_create(
            email=email,
            defaults={'is_active': True, 'email_verified': True},
        )
        if not user.email_verified:
            user.email_verified = True
            user.is_active = True
            user.save(update_fields=['email_verified', 'is_active', 'updated_at'])
        tokens = _tokens_for_user(user)
        return Response({
            'success': True,
            'data': {
                'user': {'id': str(user.id), 'email': user.email, 'role': user.role},
                'tokens': tokens,
            },
        }, status=status.HTTP_200_OK)


class LoginView(APIView):
    """
    Mobile-only login: POST with mobile + otp.
    Request OTP first via POST /api/v1/auth/register/mobile/.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        payload = {
            'mobile': request.data.get('mobile') or '',
            'otp': request.data.get('otp') or '',
        }
        ser = LoginSerializer(data=payload)
        ser.is_valid(raise_exception=True)
        user = ser.validated_data['user']
        if not user.mobile_verified or not user.is_active:
            user.mobile_verified = True
            user.is_active = True
            user.save(update_fields=['mobile_verified', 'is_active', 'updated_at'])
        tokens = _tokens_for_user(user)
        response = Response({
            'success': True,
            'data': get_verify_otp_response_data(user, tokens, request=request),
        }, status=status.HTTP_200_OK)
        if getattr(settings, 'JWT_REFRESH_COOKIE_NAME', None):
            _set_refresh_cookie(response, tokens['refresh'])
        return response


class TokenRefreshViewCustom(TokenRefreshView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        # Accept refresh from body or from HTTP-only cookie
        refresh = request.data.get('refresh') or request.COOKIES.get(
            getattr(settings, 'JWT_REFRESH_COOKIE_NAME', 'refresh_token'), ''
        )
        if refresh:
            from django.http import QueryDict
            q = QueryDict(mutable=True)
            q['refresh'] = refresh
            request._full_data = q
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200 and 'access' in response.data:
            response.data = {
                'success': True,
                'data': {'tokens': {'access': response.data['access'], 'refresh': response.data.get('refresh')}},
            }
            if response.data.get('data', {}).get('tokens', {}).get('refresh'):
                _set_refresh_cookie(response, response.data['data']['tokens']['refresh'])
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Mark user offline immediately:
        # chat/views.py considers a user online if last_seen is within 15 minutes.
        # On logout we push last_seen outside that window so UI doesn't keep showing "Online"
        # for up to 15 minutes after logout.
        try:
            mark_user_offline(request.user.pk)
        except Exception:
            pass
        # Invalidate all existing access tokens for this user.
        # Otherwise, a client that keeps using an old access token can still call APIs,
        # which would refresh last_seen and make the user appear online again.
        try:
            request.user.tokens_invalid_before = timezone.now()
            request.user.save(update_fields=["tokens_invalid_before", "updated_at"])
        except Exception:
            pass
        try:
            refresh = request.data.get('refresh')
            if refresh:
                token = RefreshToken(refresh)
                token.blacklist()
        except Exception:
            pass
        return Response({'success': True, 'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)


class PasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ser = PasswordResetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.validated_data.get('user')
        if not user:
            return Response({
                'success': True,
                'message': 'If an account exists, you will receive OTP.',
            }, status=status.HTTP_200_OK)
        email = user.email or ''
  
        mobile = user.mobile or ''
        if email:
            identifier = f'pwd_reset:email:{email}'
            otp = generate_otp(identifier)
            _send_otp_email(email, otp)
        else:
            identifier = f'pwd_reset:mobile:{mobile}'
            otp = generate_otp(identifier)
            _send_otp_mobile(mobile, otp)
        return Response({
            'success': True,
            'message': 'OTP sent for password reset.',
            'data': {'email' if email else 'mobile': email or mobile},
        }, status=status.HTTP_200_OK)


class PasswordConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ser = PasswordConfirmSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = (request.data.get('email') or '').strip()
        mobile = (request.data.get('mobile') or '').strip()
        if not email and not mobile:
            return Response({
                'success': False,
                'error': {'message': 'Provide email or mobile.'},
            }, status=status.HTTP_400_BAD_REQUEST)
        if email:
            identifier = f'pwd_reset:email:{email}'
        else:
            identifier = f'pwd_reset:mobile:{mobile}'
        ok, msg = verify_otp(identifier, ser.validated_data['otp'])
        if not ok:
            return Response({
                'success': False,
                'error': {'message': msg},
            }, status=status.HTTP_400_BAD_REQUEST)
        user = None
        if email:
            user = User.objects.filter(email=email).first()
        else:
            user = get_user_by_mobile_variants(mobile)
        if not user:
            return Response({
                'success': False,
                'error': {'message': 'User not found.'},
            }, status=status.HTTP_404_NOT_FOUND)
        user.set_password(ser.validated_data['new_password'])
        user.save(update_fields=['password', 'updated_at'])
        return Response({
            'success': True,
            'message': 'Password updated.',
        }, status=status.HTTP_200_OK)
