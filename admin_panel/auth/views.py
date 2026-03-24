import secrets

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from admin_panel.audit_log.mixins import AuditLogMixin
from admin_panel.audit_log.models import AuditLog
from admin_panel.staff_mgmt.models import StaffProfile

from .authentication import AdminJWTAuthentication
from .models import AdminUser
from .serializers import (
    AdminProfileSerializer,
    AdminProfileUpdateSerializer,
    ChangePhoneSendOTPSerializer,
    ChangePhoneVerifyOTPSerializer,
    LogoutSerializer,
    SendOTPSerializer,
    TokenRefreshSerializer,
    VerifyOTPSerializer,
    admin_permissions_for_role,
    branch_payload,
    normalize_admin_role,
)


OTP_EXPIRY_MINUTES = 10
OTP_REQUEST_LIMIT = 5
OTP_REQUEST_WINDOW_SECONDS = 10 * 60
OTP_FAILED_ATTEMPT_LIMIT = 3
OTP_LOCK_SECONDS = 30 * 60
PROFILE_PHONE_OTP_EXPIRY_SECONDS = 10 * 60
PROFILE_PHONE_OTP_REQUEST_LIMIT = 3
PROFILE_PHONE_OTP_MAX_ATTEMPTS = 3


def _err(message: str, code: int | None = None):
    payload = {"success": False, "error": {"message": message}}
    if code is not None:
        payload["error"]["code"] = code
    return payload


def _rate_key(mobile_e164: str) -> str:
    return f"admin_otp_rate:{mobile_e164}"


def _attempt_key(mobile_e164: str) -> str:
    return f"admin_otp_attempts:{mobile_e164}"


def _lock_key(mobile_e164: str) -> str:
    return f"admin_otp_lock:{mobile_e164}"


def _blacklist_key(jti: str) -> str:
    return f"admin_refresh_blacklist:{jti}"


def _profile_phone_rate_key(admin_user_id: int) -> str:
    return f"admin_profile_phone_otp_rate:{admin_user_id}"


def _profile_phone_payload_key(admin_user_id: int) -> str:
    return f"admin_profile_phone_otp_payload:{admin_user_id}"


def _sync_staff_profile_from_admin_user(user: AdminUser, *, sync_name=False, sync_email=False, sync_mobile=False):
    """
    Keep StaffProfile (admin/staff management surface) aligned with AdminUser (auth/profile surface).
    """
    if not getattr(user, "id", None):
        return
    try:
        staff = user.staff_profile
    except StaffProfile.DoesNotExist:
        return

    updates = []
    if sync_name and staff.name != user.name:
        staff.name = user.name
        updates.append("name")
    if sync_email and staff.email != user.email:
        staff.email = user.email
        updates.append("email")
    if sync_mobile:
        mobile_10 = (user.mobile or "").replace("+91", "", 1)
        if staff.mobile != mobile_10:
            staff.mobile = mobile_10
            updates.append("mobile")

    if updates:
        updates.append("updated_at")
        staff.save(update_fields=updates)


def _check_rate_limit(mobile_e164: str) -> tuple[bool, str]:
    key = _rate_key(mobile_e164)
    current = cache.get(key)
    if current is None:
        cache.set(key, 1, timeout=OTP_REQUEST_WINDOW_SECONDS)
        return True, ""
    if int(current) >= OTP_REQUEST_LIMIT:
        return False, "Too many OTP requests"
    try:
        cache.incr(key)
    except Exception:
        cache.set(key, int(current) + 1, timeout=OTP_REQUEST_WINDOW_SECONDS)
    return True, ""


def _generate_otp() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))


def _send_otp_sms(mobile_e164: str, otp: str) -> bool:
    # Prefer Celery task; fallback to sync print (same style as accounts app)
    try:
        from notifications.tasks import send_otp_sms

        send_otp_sms.delay(mobile_e164, otp)
    except Exception:
        print(f"[SMS] Admin OTP for {mobile_e164}: {otp}")
    return True


def _tokens_for_admin_user(user: AdminUser) -> dict:
    """
    Create SimpleJWT tokens without using token_blacklist DB tables.
    (Those tables are FK'd to AUTH_USER_MODEL, which is the member User model.)
    """
    refresh = RefreshToken()
    refresh["admin_user_id"] = user.pk
    refresh["role"] = user.role
    access = refresh.access_token
    access["admin_user_id"] = user.pk
    access["role"] = user.role
    return {"access": str(access), "refresh": str(refresh)}


class SendOTPView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        ser = SendOTPSerializer(data=request.data)
        if not ser.is_valid():
            if "mobile" in ser.errors:
                return Response(_err("Mobile number must be 10 digits", 400), status=status.HTTP_400_BAD_REQUEST)
            if "role" in ser.errors:
                return Response(_err("Please select a valid role", 400), status=status.HTTP_400_BAD_REQUEST)
            return Response(_err("Invalid request", 400), status=status.HTTP_400_BAD_REQUEST)

        mobile = ser.validated_data["mobile"]  # +91XXXXXXXXXX

        user = AdminUser.objects.select_related("branch").filter(mobile=mobile).first()
        if not user:
            return Response(_err("No account found for this mobile number", 404), status=status.HTTP_404_NOT_FOUND)
        if not user.is_active:
            return Response(_err("Your account has been deactivated. Contact admin.", 403), status=status.HTTP_403_FORBIDDEN)
        user_role = normalize_admin_role(user.role)
        if user.role != user_role:
            user.role = user_role
            user.save(update_fields=["role", "updated_at"])

        if cache.get(_lock_key(mobile)):
            return Response(_err("Too many failed attempts", 429), status=status.HTTP_429_TOO_MANY_REQUESTS)

        allowed, _ = _check_rate_limit(mobile)
        if not allowed:
            return Response(_err("Too many OTP requests", 429), status=status.HTTP_429_TOO_MANY_REQUESTS)

        otp = _generate_otp()
        user.otp = otp
        user.otp_expiry = timezone.now() + timezone.timedelta(minutes=OTP_EXPIRY_MINUTES)
        user.save(update_fields=["otp", "otp_expiry", "updated_at"])
        cache.delete(_attempt_key(mobile))

        _send_otp_sms(mobile, otp)

        payload = {"success": True, "message": "OTP sent successfully", "data": {"mobile": mobile}}
        if getattr(settings, "DEBUG", False):
            payload["data"]["otp"] = otp
        return Response(payload, status=status.HTTP_200_OK)


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        ser = VerifyOTPSerializer(data=request.data)
        if not ser.is_valid():
            if "mobile" in ser.errors:
                return Response(_err("Mobile number must be 10 digits", 400), status=status.HTTP_400_BAD_REQUEST)
            if "role" in ser.errors:
                return Response(_err("Please select a valid role", 400), status=status.HTTP_400_BAD_REQUEST)
            if "otp" in ser.errors:
                return Response(_err("OTP must be 6 digits", 400), status=status.HTTP_400_BAD_REQUEST)
            return Response(_err("Invalid request", 400), status=status.HTTP_400_BAD_REQUEST)

        mobile = ser.validated_data["mobile"]
        otp = ser.validated_data["otp"]

        user = AdminUser.objects.select_related("branch").filter(mobile=mobile).first()
        if not user:
            return Response(_err("No account found for this mobile number", 404), status=status.HTTP_404_NOT_FOUND)
        if not user.is_active:
            return Response(_err("Your account has been deactivated. Contact admin.", 403), status=status.HTTP_403_FORBIDDEN)
        user_role = normalize_admin_role(user.role)
        if user.role != user_role:
            user.role = user_role
            user.save(update_fields=["role", "updated_at"])

        if cache.get(_lock_key(mobile)):
            return Response(_err("Too many failed attempts", 429), status=status.HTTP_429_TOO_MANY_REQUESTS)

        if not user.otp or not user.otp_expiry or timezone.now() > user.otp_expiry:
            user.otp = None
            user.otp_expiry = None
            user.save(update_fields=["otp", "otp_expiry", "updated_at"])
            return Response(_err("OTP has expired. Please request a new one.", 400), status=status.HTTP_400_BAD_REQUEST)

        if otp != user.otp:
            attempts = int(cache.get(_attempt_key(mobile)) or 0) + 1
            cache.set(_attempt_key(mobile), attempts, timeout=OTP_EXPIRY_MINUTES * 60)
            if attempts >= OTP_FAILED_ATTEMPT_LIMIT:
                cache.set(_lock_key(mobile), "1", timeout=OTP_LOCK_SECONDS)
                return Response(_err("Too many failed attempts", 429), status=status.HTTP_429_TOO_MANY_REQUESTS)
            return Response(_err("Invalid OTP. Please try again.", 400), status=status.HTTP_400_BAD_REQUEST)

        user.otp = None
        user.otp_expiry = None
        user.last_login = timezone.now()
        user.save(update_fields=["otp", "otp_expiry", "last_login", "updated_at"])
        cache.delete(_attempt_key(mobile))
        cache.delete(_lock_key(mobile))

        tokens = _tokens_for_admin_user(user)
        return Response(
            {
                "success": True,
                "data": {
                    "access_token": tokens["access"],
                    "refresh_token": tokens["refresh"],
                    "role": user.role,
                    "name": user.name,
                    "branch": branch_payload(user),
                    "permissions": admin_permissions_for_role(user_role),
                },
            },
            status=status.HTTP_200_OK,
        )


class TokenRefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        ser = TokenRefreshSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        refresh_token = ser.validated_data["refresh_token"]
        try:
            token = RefreshToken(refresh_token)
        except TokenError:
            return Response(_err("Invalid refresh token", 401), status=status.HTTP_401_UNAUTHORIZED)

        jti = token.get("jti")
        if jti and cache.get(_blacklist_key(jti)):
            return Response(_err("Token has been blacklisted", 401), status=status.HTTP_401_UNAUTHORIZED)

        admin_user_id = token.get("admin_user_id")
        if not admin_user_id:
            return Response(_err("Invalid refresh token", 401), status=status.HTTP_401_UNAUTHORIZED)
        user = AdminUser.objects.filter(pk=admin_user_id, is_active=True).first()
        if not user:
            return Response(_err("User not found", 401), status=status.HTTP_401_UNAUTHORIZED)

        access = token.access_token
        access["admin_user_id"] = user.pk
        access["role"] = user.role
        return Response(
            {"success": True, "data": {"access_token": str(access), "refresh_token": refresh_token}},
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [AdminJWTAuthentication]

    def post(self, request):
        ser = LogoutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        refresh_token = ser.validated_data["refresh_token"]
        try:
            token = RefreshToken(refresh_token)
        except TokenError:
            return Response({"success": True, "message": "Logged out successfully."}, status=status.HTTP_200_OK)

        jti = token.get("jti")
        exp = token.get("exp")
        if jti and exp:
            expires_in = max(0, int(exp) - int(timezone.now().timestamp()))
            cache.set(_blacklist_key(jti), "1", timeout=expires_in)

        return Response({"success": True, "message": "Logged out successfully."}, status=status.HTTP_200_OK)


class AdminMyProfileView(AuditLogMixin, APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [AdminJWTAuthentication]

    def get(self, request):
        return Response(
            {"success": True, "data": AdminProfileSerializer(request.user).data},
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        patch_data = {
            "name": request.data.get("name"),
            "email": request.data.get("email"),
        }
        ser = AdminProfileUpdateSerializer(data=patch_data, context={"user": request.user})
        if not ser.is_valid():
            errors = ser.errors
            if "name" in errors:
                return Response(_err(str(errors["name"][0]), 400), status=status.HTTP_400_BAD_REQUEST)
            if "email" in errors:
                msg = str(errors["email"][0])
                if msg == "Enter a valid email address.":
                    return Response(_err(msg, 400), status=status.HTTP_400_BAD_REQUEST)
                return Response(_err(msg, 400), status=status.HTTP_400_BAD_REQUEST)
            return Response(_err("Invalid request", 400), status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        old_value = {"name": user.name, "email": user.email}
        user.name = ser.validated_data["name"]
        user.email = ser.validated_data["email"]
        try:
            user.save(update_fields=["name", "email", "updated_at"])
            _sync_staff_profile_from_admin_user(user, sync_name=True, sync_email=True)
        except IntegrityError:
            return Response(
                _err("Profile email/mobile conflicts with another staff account.", 400),
                status=status.HTTP_400_BAD_REQUEST,
            )
        self.log_action(
            action=AuditLog.ACTION_STAFF_UPDATE,
            resource=f"admin_user:{user.id}",
            details="Admin profile updated.",
            old_value=old_value,
            new_value={"name": user.name, "email": user.email},
        )
        return Response(
            {"success": True, "data": AdminProfileSerializer(user).data},
            status=status.HTTP_200_OK,
        )


class AdminChangePhoneSendOTPView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [AdminJWTAuthentication]

    def post(self, request):
        ser = ChangePhoneSendOTPSerializer(data=request.data, context={"user": request.user})
        if not ser.is_valid():
            errors = ser.errors
            if "new_mobile" in errors:
                return Response(_err(str(errors["new_mobile"][0]), 400), status=status.HTTP_400_BAD_REQUEST)
            return Response(_err("Invalid request", 400), status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        rate_key = _profile_phone_rate_key(user.id)
        current = int(cache.get(rate_key) or 0)
        if current >= PROFILE_PHONE_OTP_REQUEST_LIMIT:
            return Response(_err("Too many OTP requests.", 429), status=status.HTTP_429_TOO_MANY_REQUESTS)
        if current == 0:
            cache.set(rate_key, 1, timeout=OTP_REQUEST_WINDOW_SECONDS)
        else:
            try:
                cache.incr(rate_key)
            except Exception:
                cache.set(rate_key, current + 1, timeout=OTP_REQUEST_WINDOW_SECONDS)

        new_mobile = ser.validated_data["new_mobile"]
        otp = _generate_otp()
        cache.set(
            _profile_phone_payload_key(user.id),
            {"mobile": new_mobile, "otp": otp, "attempts": 0},
            timeout=PROFILE_PHONE_OTP_EXPIRY_SECONDS,
        )
        _send_otp_sms(new_mobile, otp)

        payload = {"success": True, "message": "OTP sent successfully.", "data": {"new_mobile": new_mobile}}
        if getattr(settings, "DEBUG", False):
            payload["data"]["otp"] = otp
        return Response(payload, status=status.HTTP_200_OK)


class AdminChangePhoneVerifyOTPView(AuditLogMixin, APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [AdminJWTAuthentication]

    def post(self, request):
        ser = ChangePhoneVerifyOTPSerializer(data=request.data)
        if not ser.is_valid():
            errors = ser.errors
            if "new_mobile" in errors:
                return Response(_err(str(errors["new_mobile"][0]), 400), status=status.HTTP_400_BAD_REQUEST)
            if "otp" in errors:
                return Response(_err(str(errors["otp"][0]), 400), status=status.HTTP_400_BAD_REQUEST)
            return Response(_err("Invalid request", 400), status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        payload_key = _profile_phone_payload_key(user.id)
        cached = cache.get(payload_key)
        if not cached:
            return Response(
                _err("OTP has expired. Please request a new one.", 400),
                status=status.HTTP_400_BAD_REQUEST,
            )

        requested_mobile = cached.get("mobile")
        input_mobile = ser.validated_data["new_mobile"]
        if requested_mobile != input_mobile:
            return Response(
                _err("Mobile number does not match the OTP request.", 400),
                status=status.HTTP_400_BAD_REQUEST,
            )

        attempts = int(cached.get("attempts") or 0)
        if attempts >= PROFILE_PHONE_OTP_MAX_ATTEMPTS:
            return Response(
                _err("Too many failed OTP attempts.", 429),
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if cached.get("otp") != ser.validated_data["otp"]:
            attempts += 1
            if attempts >= PROFILE_PHONE_OTP_MAX_ATTEMPTS:
                cache.delete(payload_key)
                return Response(
                    _err("Too many failed OTP attempts.", 429),
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            cached["attempts"] = attempts
            cache.set(payload_key, cached, timeout=PROFILE_PHONE_OTP_EXPIRY_SECONDS)
            return Response(_err("Invalid OTP.", 400), status=status.HTTP_400_BAD_REQUEST)

        if AdminUser.objects.exclude(pk=user.pk).filter(mobile=input_mobile).exists():
            return Response(
                _err("This mobile number is already registered to another account.", 400),
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_mobile = user.mobile
        user.mobile = input_mobile
        try:
            user.save(update_fields=["mobile", "updated_at"])
            _sync_staff_profile_from_admin_user(user, sync_mobile=True)
        except IntegrityError:
            return Response(
                _err("This mobile number is already registered to another staff account.", 400),
                status=status.HTTP_400_BAD_REQUEST,
            )
        cache.delete(payload_key)

        self.log_action(
            action=AuditLog.ACTION_STAFF_UPDATE,
            resource=f"admin_user:{user.id}",
            details="Admin mobile updated via OTP verification.",
            old_value={"mobile": old_mobile},
            new_value={"mobile": user.mobile},
        )

        return Response(
            {"success": True, "message": "Mobile number updated successfully.", "data": AdminProfileSerializer(user).data},
            status=status.HTTP_200_OK,
        )

