from django.contrib import admin
from .models import Plan, ServiceCharge, UserPlan, Transaction, ProfileView, Interest


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'price', 'duration_days',
        'profile_view_limit', 'interest_limit', 'chat_limit',
        'horoscope_match_limit', 'contact_view_limit',
        'is_active', 'created_at',
    )
    list_filter = ('is_active',)


@admin.register(ServiceCharge)
class ServiceChargeAdmin(admin.ModelAdmin):
    list_display = ('gender', 'amount')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'plan', 'total_amount', 'payment_method', 'payment_status', 'created_at')
    list_filter = ('payment_method', 'payment_status')
    raw_id_fields = ('user',)


@admin.register(UserPlan)
class UserPlanAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'plan', 'price_paid', 'service_charge', 'service_charge_paid',
        'profile_views_used', 'interests_used', 'chat_used',
        'horoscope_used', 'contact_views_used',
        'valid_from', 'valid_until', 'is_active',
    )
    list_filter = ('plan',)
    raw_id_fields = ('user',)


@admin.register(ProfileView)
class ProfileViewAdmin(admin.ModelAdmin):
    list_display = ('viewer', 'profile', 'last_viewed_at', 'created_at')
    list_filter = ('created_at', 'last_viewed_at')
    raw_id_fields = ('viewer', 'profile')


@admin.register(Interest)
class InterestAdmin(admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'status', 'created_at')
    list_filter = ('status',)
    raw_id_fields = ('sender', 'receiver')
