"""
Auth serializers: register, verify, login, password reset.
"""
import phonenumbers
import re
from datetime import datetime, date

from rest_framework import serializers

from core.dob_utils import parse_registration_dob_string, validate_matrimony_registration_dob
from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError

User = get_user_model()

# Match accounts.models.User (avoid import-order issues with get_user_model)
GENDER_CHOICES = [('M', 'Male'), ('F', 'Female'), ('O', 'Other')]
PROFILE_FOR_CHOICES = [
    ('myself', 'Myself'),
    ('son', 'Son'),
    ('daughter', 'Daughter'),
    ('brother', 'Brother'),
    ('sister', 'Sister'),
    ('friend', 'Friend'),
    ('relative', 'Relative'),
]


def validate_phone_number(phone):
    """
    Enforce +91 followed by 10 digits.
    """
    phone = (phone or '').strip()
    if not phone:
        raise serializers.ValidationError('Phone number is required.')
    if not re.fullmatch(r"\+91\d{10}", phone):
        raise serializers.ValidationError('Invalid phone number format. Use +91XXXXXXXXXX.')
    return phone


def mobile_variants(phone: str) -> tuple[str, str, str]:
    """Return equivalent variants for compatibility lookups."""
    canonical = validate_phone_number(phone)
    digits = canonical[-10:]
    return canonical, f"91{digits}", digits


def get_user_by_mobile_variants(phone: str):
    canonical, prefixed, digits = mobile_variants(phone)
    return User.objects.filter(mobile__in=[canonical, prefixed, digits]).order_by("-created_at").first()


def mobile_exists_any_variant(phone: str, *, verified_only: bool = False) -> bool:
    canonical, prefixed, digits = mobile_variants(phone)
    qs = User.objects.filter(mobile__in=[canonical, prefixed, digits])
    if verified_only:
        qs = qs.filter(mobile_verified=True)
    return qs.exists()


def parse_dob(dob_str):
    """
    Parse registration-style DOB (DD-MM-YYYY or DD/MM/YYYY). Returns date object.
    """
    try:
        return parse_registration_dob_string(dob_str)
    except ValueError as e:
        raise serializers.ValidationError(str(e)) from e


def parse_optional_dob(dob_str):
    """
    For PATCH profile basic: None or blank -> None; else DD-MM-YYYY or YYYY-MM-DD.
    """
    if dob_str is None:
        return None
    s = str(dob_str).strip()
    if not s:
        return None
    for fmt in ('%d-%m-%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise serializers.ValidationError(
        'Date has wrong format. Use DD-MM-YYYY (YYYY-MM-DD is also accepted).'
    )


class DOBField(serializers.Field):
    """
    Accepts DOB as string in DD-MM-YYYY or DD/MM/YYYY. Never use DateField (which expects YYYY-MM-DD).
    """
    def to_internal_value(self, data):
        if data is None or (isinstance(data, str) and not data.strip()):
            raise serializers.ValidationError('Date of birth is required.')
        return str(data).strip()


# --- New registration flow (name, phone, email, dob, gender) ---

class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=True)
    phone_number = serializers.CharField(required=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    dob = DOBField(required=True)
    gender = serializers.ChoiceField(choices=GENDER_CHOICES, required=True)
    profile_for = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_profile_for(self, value):
        """Normalize to lowercase; must be one of: myself, son, daughter, brother, sister, friend, relative."""
        if not value or not str(value).strip():
            return None
        val = str(value).strip().lower()
        allowed = {c[0] for c in PROFILE_FOR_CHOICES}
        if val not in allowed:
            raise serializers.ValidationError(
                f'Must be one of: {", ".join(sorted(allowed))}'
            )
        return val

    def validate_email(self, value):
        if not value or not str(value).strip():
            return None
        value = value.strip().lower()
        try:
            validate_email(value)
        except DjangoValidationError:
            raise serializers.ValidationError('Invalid email address')
        return value

    def validate(self, attrs):
        try:
            attrs['phone_number'] = validate_phone_number(attrs['phone_number'])
        except serializers.ValidationError as e:
            raise serializers.ValidationError({'phone_number': e.detail})
        try:
            dob_parsed = parse_registration_dob_string(attrs['dob'])
            validate_matrimony_registration_dob(dob_parsed, attrs['gender'])
        except ValueError as e:
            raise serializers.ValidationError({'dob': str(e)})
        attrs['dob'] = dob_parsed
        phone = attrs['phone_number']
        email = (attrs.get('email') or '').strip().lower()
        # is_registered = mobile_verified (user has completed OTP verification)
        if mobile_exists_any_variant(phone, verified_only=True):
            raise serializers.ValidationError({
                'non_field_errors': ['Phone number already registered'],
            })
        if email and User.objects.filter(email__iexact=email, mobile_verified=True).exists():
            raise serializers.ValidationError({
                'non_field_errors': ['Email already registered'],
            })
        if email:
            taken = User.objects.filter(email__iexact=email).exclude(mobile=phone).exists()
            if taken:
                raise serializers.ValidationError({
                    'non_field_errors': ['Email already registered'],
                })
        return attrs


class ResendOTPSerializer(serializers.Serializer):
    """Resend login OTP for an existing verified account (E164 phone_number)."""

    phone_number = serializers.CharField(required=True)

    def validate_phone_number(self, value):
        return validate_phone_number(value)


class VerifyOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20, required=False)
    mobile = serializers.CharField(max_length=20, required=False)
    otp = serializers.CharField(max_length=6, min_length=6, required=True)

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError('OTP must be 6 digits.')
        return value

    def validate(self, data):
        raw_phone = (data.get('phone_number') or data.get('mobile') or '').strip()
        if not raw_phone:
            raise serializers.ValidationError({'phone_number': 'Provide phone_number or mobile.'})
        try:
            phone = validate_phone_number(raw_phone)
        except serializers.ValidationError:
            try:
                parsed = phonenumbers.parse(raw_phone, 'IN')
                if phonenumbers.is_valid_number(parsed):
                    phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                else:
                    phone = raw_phone
            except Exception:
                phone = raw_phone
        data['phone_number'] = phone
        from .services import verify_otp, pop_pending_registration
        identifier = f"phone:{data['phone_number']}"
        ok, msg = verify_otp(identifier, data['otp'])
        if not ok:
            raise serializers.ValidationError(msg)
        pending = pop_pending_registration(data['phone_number'])
        if pending:
            from datetime import date
            dob_val = pending['dob']
            if isinstance(dob_val, str):
                dob_val = date.fromisoformat(dob_val)
            user = User.objects.create_user(
                email=pending.get('email') or None,
                mobile=data['phone_number'],
                password=User.objects.make_random_password(),
                name=pending['name'],
                dob=dob_val,
                gender=pending['gender'],
                profile_for=pending.get('profile_for') or None,
                mobile_verified=True,
                is_active=True,
            )
        else:
            user = get_user_by_mobile_variants(data['phone_number'])
            if not user:
                raise serializers.ValidationError(
                    'Registration session expired or invalid. Please register again and verify the OTP.',
                )
            if not user.mobile_verified or not user.is_active:
                user.mobile_verified = True
                user.is_active = True
                user.save(update_fields=['mobile_verified', 'is_active', 'updated_at'])
        data['user'] = user
        return data


def get_verify_otp_response_data(user, tokens, request=None):
    """
    Build the full data payload for POST /api/v1/auth/verify-otp/ response.
    Includes tokens, matri_id, registration flags, profile completion fields,
    and all previously saved profile data in detail.
    """
    from profiles.utils import get_profile_completion_data, get_full_profile_data
    completion = get_profile_completion_data(user)
    profile_data = get_full_profile_data(user, request=request)
    return {
        'access_token': tokens['access'],
        'refresh_token': tokens['refresh'],
        'matri_id': user.matri_id,
        'is_registered': True,
        'is_registration_profile_completed': getattr(
            user, 'is_registration_profile_completed', False
        ),
        'profile_status': completion['profile_status'],
        'profile_steps': completion['profile_steps'],
        'profile_completion_percentage': completion['profile_completion_percentage'],
        'next_step': completion['next_step'],
        'profile': profile_data,
    }


class RegisterMobileSerializer(serializers.Serializer):
    mobile = serializers.CharField(max_length=20)

    def validate_mobile(self, value):
        return validate_phone_number(value)


class VerifyMobileSerializer(serializers.Serializer):
    mobile = serializers.CharField(max_length=20)
    otp = serializers.CharField(max_length=6, min_length=6)
    referral_code = serializers.CharField(required=False, allow_blank=True)

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError('OTP must be 6 digits.')
        return value


class RegisterEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=6)
    referral_code = serializers.CharField(required=False, allow_blank=True)

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError('OTP must be 6 digits.')
        return value


class LoginSerializer(serializers.Serializer):
    """Mobile-only login: mobile + otp. Request OTP first via POST /api/v1/auth/register/mobile/."""
    mobile = serializers.CharField()
    otp = serializers.CharField(max_length=6, min_length=6)

    def validate_mobile(self, value):
        return validate_phone_number(value)

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError('OTP must be 6 digits.')
        return value

    def validate(self, data):
        mobile = (data.get('mobile') or '').strip()
        if not mobile:
            raise serializers.ValidationError('Mobile number is required.')
        identifier = f'mobile:{mobile}'
        from .services import verify_otp
        ok, msg = verify_otp(identifier, data['otp'])
        if not ok:
            raise serializers.ValidationError(msg)
        user = get_user_by_mobile_variants(mobile)
        if not user:
            raise serializers.ValidationError('User not found.')
        # Activate account on successful OTP (so no "Account is not active" anywhere)
        if not user.mobile_verified or not user.is_active:
            user.mobile_verified = True
            user.is_active = True
            user.save(update_fields=['mobile_verified', 'is_active', 'updated_at'])
        data['user'] = user
        return data


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    mobile = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        email = data.get('email') or ''
        mobile = data.get('mobile') or ''
        if not email and not mobile:
            raise serializers.ValidationError('Provide email or mobile.')
        user = None
        if email:
            user = User.objects.filter(email=email).first()
        else:
            user = get_user_by_mobile_variants(mobile)
        data['user'] = user
        return data


class PasswordConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    mobile = serializers.CharField(required=False, allow_blank=True)
    otp = serializers.CharField(max_length=6, min_length=6)
    new_password = serializers.CharField(write_only=True, style={'input_type': 'password'}, min_length=8)

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError('OTP must be 6 digits.')
        return value
