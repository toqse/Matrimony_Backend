from django.contrib import admin
from .models import User, OTPRecord


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
