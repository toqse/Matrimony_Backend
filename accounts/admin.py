from django import forms
from django.contrib import admin

from .models import User, OTPRecord, DummyOTPPhone


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['matri_id', 'email', 'name', 'mobile', 'gender', 'role', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'gender']
    search_fields = ['email', 'mobile', 'name', 'matri_id']
    ordering = ['-created_at']
    readonly_fields = ['matri_id', 'created_at', 'updated_at']
    fieldsets = (
        ('Account Info', {'fields': ('matri_id', 'email', 'mobile', 'password')}),
        ('Personal Details', {'fields': ('name', 'dob', 'gender', 'branch', 'role')}),
        (
            'Status & Permissions',
            {
                'fields': (
                    'is_active',
                    'is_staff',
                    'is_superuser',
                    'email_verified',
                    'mobile_verified',
                    'is_registration_profile_completed',
                )
            },
        ),
        ('Timestamps', {'fields': ('last_seen', 'created_at', 'updated_at')}),
    )


@admin.register(OTPRecord)
class OTPRecordAdmin(admin.ModelAdmin):
    list_display = ['identifier', 'attempts', 'expires_at', 'verified', 'created_at']


class DummyOTPPhoneAdminForm(forms.ModelForm):
    class Meta:
        model = DummyOTPPhone
        fields = ['phone', 'dummy_otp', 'is_active', 'note']

    def clean_phone(self):
        from django.core.exceptions import ValidationError
        from core.phone import extract_indian_mobile_10

        phone = self.cleaned_data.get('phone')
        mobile_10 = extract_indian_mobile_10(phone)
        if not mobile_10:
            raise ValidationError(
                'Enter a valid 10-digit Indian mobile number (starting with 6-9).'
            )
        return f'+91{mobile_10}'

    def clean_dummy_otp(self):
        from django.conf import settings
        from django.core.exceptions import ValidationError

        otp = (self.cleaned_data.get('dummy_otp') or '').strip()
        length = getattr(settings, 'OTP_LENGTH', 6)
        if not otp.isdigit() or len(otp) != length:
            raise ValidationError(f'Dummy OTP must be exactly {length} digits.')
        return otp


@admin.register(DummyOTPPhone)
class DummyOTPPhoneAdmin(admin.ModelAdmin):
    form = DummyOTPPhoneAdminForm
    list_display = ['phone', 'dummy_otp', 'is_active', 'note', 'updated_at']
    list_filter = ['is_active']
    search_fields = ['phone', 'note']
    ordering = ['-updated_at']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        (
            None,
            {
                'fields': ('phone', 'dummy_otp', 'is_active', 'note'),
                'description': (
                    'For listed phones, both the real OTP sent by the backend '
                    'and this dummy OTP will work for register/login verification.'
                ),
            },
        ),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )
