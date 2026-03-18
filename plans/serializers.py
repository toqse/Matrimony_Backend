"""
Serializers for Plan, UserPlan, Transaction.
"""
from rest_framework import serializers
from django.core.exceptions import ObjectDoesNotExist

from .models import Plan, ServiceCharge, UserPlan, Transaction, Interest
from matches.utils import age_from_dob
from profiles.models import UserLocation, UserEducation, UserPhotos
from core.media import absolute_media_url


class PlanSerializer(serializers.ModelSerializer):
    """Admin CRUD: full plan fields."""
    class Meta:
        model = Plan
        fields = [
            'id', 'name', 'price', 'duration_days',
            'profile_view_limit', 'interest_limit', 'chat_limit',
            'horoscope_match_limit', 'contact_view_limit',
            'description', 'is_active', 'created_at',
        ]
        read_only_fields = ['created_at']


class PlanListForUserSerializer(serializers.Serializer):
    """Plan with service_charge and total_price for listing to users."""
    id = serializers.IntegerField()
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    service_charge = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    duration_days = serializers.IntegerField()
    profile_view_limit = serializers.IntegerField()
    interest_limit = serializers.IntegerField()
    chat_limit = serializers.IntegerField()
    horoscope_match_limit = serializers.IntegerField()
    contact_view_limit = serializers.IntegerField()
    description = serializers.CharField(allow_blank=True)


class PlanPurchaseSerializer(serializers.Serializer):
    """Body for POST /api/v1/plans/purchase/.

    payment_option:
      plan_only — pay only the plan registration fee (plan.price).
      full      — pay the remaining amount (service_charge - plan.price) upfront.
    """
    PAYMENT_OPTION_PLAN_ONLY = 'plan_only'
    PAYMENT_OPTION_FULL = 'full'

    plan_id = serializers.IntegerField()
    payment_method = serializers.ChoiceField(
        choices=[
            Transaction.PAYMENT_RAZORPAY,
            Transaction.PAYMENT_STRIPE,
            Transaction.PAYMENT_UPI,
            Transaction.PAYMENT_MANUAL,
        ],
        default=Transaction.PAYMENT_MANUAL,
    )
    payment_option = serializers.ChoiceField(
        choices=[PAYMENT_OPTION_PLAN_ONLY, PAYMENT_OPTION_FULL],
        default=PAYMENT_OPTION_PLAN_ONLY,
        help_text=(
            'plan_only: pay only the plan registration fee. '
            'full: pay service_charge minus plan price upfront.'
        ),
    )

    def validate_plan_id(self, value):
        if not Plan.objects.filter(pk=value, is_active=True).exists():
            raise serializers.ValidationError('Invalid or inactive plan.')
        return value


class PayRemainingServiceSerializer(serializers.Serializer):
    """Body for POST /api/v1/plans/pay-remaining-service/."""
    payment_method = serializers.ChoiceField(
        choices=[
            Transaction.PAYMENT_RAZORPAY,
            Transaction.PAYMENT_STRIPE,
            Transaction.PAYMENT_UPI,
            Transaction.PAYMENT_MANUAL,
        ],
        default=Transaction.PAYMENT_MANUAL,
    )


class TransactionSerializer(serializers.ModelSerializer):
    """Transaction list/detail (admin or user's own)."""
    plan_name = serializers.CharField(source='plan.name', read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id', 'user', 'plan', 'plan_name',
            'amount', 'service_charge', 'total_amount',
            'payment_method', 'payment_status',
            'transaction_id', 'created_at',
        ]
        read_only_fields = fields


class InterestSerializer(serializers.ModelSerializer):
    """Basic serializer for Interest model."""

    class Meta:
        model = Interest
        fields = ['id', 'sender', 'receiver', 'status', 'created_at']
        read_only_fields = ['id', 'sender', 'receiver', 'created_at']


def _get_user_brief_profile(user, request=None):
    """
    Return brief profile dict for interest cards:
    matri_id, name, age, location, education, occupation, profile_photo.
    """
    if not user:
        return {
            'matri_id': '',
            'name': '',
            'age': None,
            'location': None,
            'education': None,
            'occupation': None,
            'profile_photo': None,
        }

    # Age from DOB
    age = age_from_dob(getattr(user, 'dob', None))

    # Location: "City, State"
    try:
        loc = user.user_location
    except ObjectDoesNotExist:
        loc = None
    city = getattr(getattr(loc, 'city', None), 'name', None)
    state = getattr(getattr(loc, 'state', None), 'name', None)
    if city and state:
        location = f'{city}, {state}'
    else:
        location = city or state or None

    # Education & occupation
    try:
        edu = user.user_education
    except ObjectDoesNotExist:
        edu = None
    education = getattr(getattr(edu, 'highest_education', None), 'name', None)
    occupation = getattr(getattr(edu, 'occupation', None), 'name', None)

    # Profile photo URL
    try:
        photos = user.user_photos
    except ObjectDoesNotExist:
        photos = None
    profile_photo = absolute_media_url(request, photos.profile_photo) if photos and photos.profile_photo else None

    return {
        'matri_id': user.matri_id or '',
        'name': user.name or '',
        'age': age,
        'location': location,
        'education': education,
        'occupation': occupation,
        'profile_photo': profile_photo,
    }


class InterestListSerializer(serializers.Serializer):
    """
    Serializer for listing interests with brief profile data.
    Expects context['direction'] = 'sent' or 'received'.
    """

    interest_id = serializers.IntegerField(source='id')
    matri_id = serializers.CharField()
    name = serializers.CharField()
    age = serializers.IntegerField(allow_null=True)
    location = serializers.CharField(allow_null=True)
    education = serializers.CharField(allow_null=True)
    occupation = serializers.CharField(allow_null=True)
    profile_photo = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    created_at = serializers.DateTimeField()

    def to_representation(self, instance):
        request = self.context.get('request')
        direction = self.context.get('direction')
        if direction == 'sent':
            other_user = instance.receiver
        else:
            other_user = instance.sender

        profile = _get_user_brief_profile(other_user, request=request)

        return {
            'interest_id': instance.id,
            'matri_id': profile['matri_id'],
            'name': profile['name'],
            'age': profile['age'],
            'location': profile['location'],
            'education': profile['education'],
            'occupation': profile['occupation'],
            'profile_photo': profile['profile_photo'],
            'status': instance.status,
            'created_at': instance.created_at,
        }
