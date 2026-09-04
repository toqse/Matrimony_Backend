from django.contrib import admin
from .models import (
    Plan,
    ServiceCharge,
    UserPlan,
    Transaction,
    ProfileView,
    Interest,
    RazorpayOrder,
    RazorpayWebhookEvent,
)


class ReadOnlyModelAdmin(admin.ModelAdmin):
    """View existing rows; no add, edit, or delete."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        names = [field.name for field in self.model._meta.fields]
        extra = list(self.readonly_fields or [])
        return tuple(dict.fromkeys(extra + names))


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'price', 'duration_days',
        'profile_view_limit', 'interest_limit', 'chat_limit',
        'horoscope_match_limit', 'contact_view_limit',
        'is_published', 'is_active', 'created_at',
    )
    list_filter = ('is_published', 'is_active',)


@admin.register(ServiceCharge)
class ServiceChargeAdmin(admin.ModelAdmin):
    list_display = ('gender', 'amount')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'plan', 'transaction_type', 'total_amount',
        'payment_method', 'payment_status', 'transaction_id', 'created_at',
    )
    list_filter = ('payment_method', 'payment_status', 'transaction_type')
    search_fields = ('transaction_id', 'user__matri_id', 'user__name', 'user__email')
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


@admin.register(RazorpayOrder)
class RazorpayOrderAdmin(ReadOnlyModelAdmin):
    list_display = (
        'razorpay_order_id',
        'user',
        'purpose',
        'amount_paise',
        'status',
        'razorpay_payment_id',
        'transaction',
        'created_at',
    )
    list_filter = ('status', 'purpose')
    search_fields = (
        'razorpay_order_id',
        'razorpay_payment_id',
        'receipt',
        'user__matri_id',
        'user__name',
    )
    raw_id_fields = ('user', 'plan', 'transaction')
    date_hierarchy = 'created_at'


@admin.register(RazorpayWebhookEvent)
class RazorpayWebhookEventAdmin(ReadOnlyModelAdmin):
    list_display = (
        'created_at',
        'event',
        'signature_valid',
        'status',
        'http_status',
        'razorpay_order_id',
        'razorpay_payment_id',
    )
    list_filter = ('status', 'event', 'signature_valid')
    search_fields = (
        'razorpay_order_id',
        'razorpay_payment_id',
        'event',
        'error_message',
    )
    raw_id_fields = ('order', 'transaction')
    date_hierarchy = 'created_at'
