"""
Plans app: Plan, ServiceCharge, UserPlan, Transaction, ProfileView, Interest.
Subscription plans, service charges, purchases and usage tracking.
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from core.models import TimeStampedModel


class Plan(TimeStampedModel):
    """Subscription plan definition: price, limits and duration."""
    name = models.CharField(max_length=100)
    price = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Plan price (before service charge)'
    )
    duration_days = models.PositiveIntegerField(
        default=30,
        help_text='Plan validity in days'
    )
    profile_view_limit = models.PositiveIntegerField(
        default=0,
        help_text='Number of full profile views allowed; 0 = unlimited'
    )
    interest_limit = models.PositiveIntegerField(
        default=0,
        help_text='Number of interests allowed to send; 0 = unlimited'
    )
    chat_limit = models.PositiveIntegerField(
        default=0,
        help_text='Number of chat initiations; 0 = unlimited'
    )
    horoscope_match_limit = models.PositiveIntegerField(
        default=0,
        help_text='Number of horoscope matches allowed; 0 = unlimited'
    )
    contact_view_limit = models.PositiveIntegerField(
        default=0,
        help_text='Number of contact views allowed; 0 = unlimited'
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'plans_plan'
        ordering = ['name']

    def __str__(self):
        return self.name


class ServiceCharge(TimeStampedModel):
    """Service charge by gender (Male=15000 remaining 14501, Female=10000 remaining 9501, Other=5000)."""
    GENDER_M = 'M'
    GENDER_F = 'F'
    GENDER_O = 'O'
    GENDER_CHOICES = [
        (GENDER_M, 'Male'),
        (GENDER_F, 'Female'),
        (GENDER_O, 'Other'),
    ]
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = 'plans_service_charge'
        ordering = ['gender']

    def __str__(self):
        return f'{self.get_gender_display()}: {self.amount}'


class UserPlan(TimeStampedModel):
    """User's subscription: plan, price paid, usage counters, validity."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='user_plan'
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name='user_plans'
    )
    price_paid = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Plan price at time of purchase'
    )
    service_charge = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Total service charge at purchase (by gender)'
    )
    service_charge_paid = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Amount of service charge paid so far (first payment 499, then remaining 14501)'
    )
    # Carry-forward / bonus quotas added on upgrade (effective_limit = plan.limit + bonus).
    # These are applied only when plan.limit > 0 (0 = unlimited).
    profile_view_bonus = models.PositiveIntegerField(default=0)
    interest_bonus = models.PositiveIntegerField(default=0)
    chat_bonus = models.PositiveIntegerField(default=0)
    horoscope_bonus = models.PositiveIntegerField(default=0)
    contact_view_bonus = models.PositiveIntegerField(default=0)
    profile_views_used = models.PositiveIntegerField(default=0)
    interests_used = models.PositiveIntegerField(default=0)
    chat_used = models.PositiveIntegerField(default=0)
    horoscope_used = models.PositiveIntegerField(default=0)
    contact_views_used = models.PositiveIntegerField(default=0)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'plans_user_plan'
        verbose_name = 'User plan'
        verbose_name_plural = 'User plans'

    def __str__(self):
        return f'{self.user.matri_id} - {self.plan.name}'


class Transaction(TimeStampedModel):
    """Payment transaction for plan purchase, profile boost or refund."""
    PAYMENT_RAZORPAY = 'razorpay'
    PAYMENT_STRIPE = 'stripe'
    PAYMENT_UPI = 'upi'
    PAYMENT_MANUAL = 'manual'
    PAYMENT_METHOD_CHOICES = [
        (PAYMENT_RAZORPAY, 'Razorpay'),
        (PAYMENT_STRIPE, 'Stripe'),
        (PAYMENT_UPI, 'UPI'),
        (PAYMENT_MANUAL, 'Manual (Admin approval)'),
    ]
    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_REFUNDED = 'refunded'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_REFUNDED, 'Refunded'),
    ]
    TYPE_PLAN_PURCHASE = 'plan_purchase'
    TYPE_PROFILE_BOOST = 'profile_boost'
    TYPE_REFUND = 'refund'
    TYPE_CHOICES = [
        (TYPE_PLAN_PURCHASE, 'Plan Purchase'),
        (TYPE_PROFILE_BOOST, 'Profile Boost'),
        (TYPE_REFUND, 'Refund'),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='plan_transactions'
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name='transactions',
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    service_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default=PAYMENT_MANUAL
    )
    payment_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_PLAN_PURCHASE,
    )
    transaction_id = models.CharField(max_length=255, blank=True, db_index=True)

    class Meta:
        db_table = 'plans_transaction'
        ordering = ['-created_at']

    def __str__(self):
        plan_name = self.plan.name if self.plan_id else self.get_transaction_type_display()
        return f'{self.user.matri_id} - {plan_name} - {self.total_amount}'


class ProfileView(TimeStampedModel):
    """Track when a user views another user's full profile."""
    viewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile_views_made'
    )
    viewed_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile_views_received'
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'plans_profile_view'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['viewer', 'viewed_user']),
            models.Index(fields=['viewer', 'timestamp']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['viewer', 'viewed_user'], name='uniq_profile_view_pair'),
        ]

    def __str__(self):
        return f'{self.viewer.matri_id} viewed {self.viewed_user.matri_id}'


class Conversation(TimeStampedModel):
    """
    Simple two-user conversation model for chat.
    One row per unique pair (user1, user2) with user1_id < user2_id.
    """
    user1 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversations_as_user1',
    )
    user2 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversations_as_user2',
    )

    class Meta:
        db_table = 'chat_conversation'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user1', 'user2'], name='uniq_conversation_pair'),
        ]

    def __str__(self):
        return f'Conversation between {self.user1.matri_id} and {self.user2.matri_id}'

    def other_user(self, user):
        """Return the other participant in the conversation."""
        return self.user2 if user.pk == self.user1_id else self.user1


class Message(TimeStampedModel):
    """Chat message within a conversation."""
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_messages_sent',
    )
    text = models.TextField()
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'chat_message'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.sender.matri_id} in conv {self.conversation_id}: {self.text[:30]}'


class Interest(TimeStampedModel):
    """Interest sent from one user to another."""
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_REJECTED = 'rejected'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='interests_sent'
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='interests_received'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'plans_interest'
        ordering = ['-created_at']
        unique_together = [['sender', 'receiver']]
        indexes = [
            models.Index(fields=['sender', 'receiver']),
        ]

    def __str__(self):
        return f'{self.sender.matri_id} -> {self.receiver.matri_id}'
