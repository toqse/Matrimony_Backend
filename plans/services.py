"""
Plan limit checks and PlanLimitService: can_view_profile, can_send_interest, can_chat, can_view_contact.
Returns (allowed: bool, remaining: int or None for unlimited).
Each action can decrement usage when the service is used.
"""
from django.utils import timezone


def _get_user_plan(user):
    """Return active UserPlan if valid_until >= today, is_active and plan is active."""
    from .models import UserPlan
    if not user or not user.is_authenticated:
        return None
    try:
        up = user.user_plan
    except Exception:
        return None
    if not getattr(up, 'is_active', True):
        return None
    plan = getattr(up, 'plan', None)
    if not plan or not getattr(plan, 'is_active', True):
        return None
    if up.valid_until and up.valid_until < timezone.now().date():
        return None
    return up


def _effective_service_charge_paid(user_plan, *, repair_legacy=False):
    """
    Bureau fee credited so far. plan_only purchases count the registration fee
    (price_paid) toward service charge. Legacy rows may have price_paid set but
    service_charge_paid stuck at 0 (e.g. staff-recorded sales before fix).
    """
    from decimal import Decimal

    paid = Decimal(str(getattr(user_plan, 'service_charge_paid', None) or 0))
    price_paid = Decimal(str(getattr(user_plan, 'price_paid', None) or 0))
    if paid <= 0 and price_paid > 0:
        if repair_legacy:
            user_plan.service_charge_paid = price_paid
            user_plan.save(update_fields=['service_charge_paid', 'updated_at'])
        return price_paid
    return paid


def user_has_active_plan(user):
    """True when the user has a valid, non-expired active subscription (same as get_user_plan_status == 'active')."""
    return get_user_plan_status(user) == 'active'


def has_unlocked_profile(viewer, profile_up):
    """True when viewer has a paid unlock (not merely analytics) for this UserProfile."""
    if not viewer or not profile_up:
        return False
    from .models import ProfileView
    return ProfileView.objects.filter(
        viewer=viewer,
        profile=profile_up,
        unlocked=True,
    ).exists()


def can_open_full_profile(viewer, profile_up):
    """
    Whether viewer may see full contact/family for profile_up.
    Returns (allowed: bool, already_unlocked: bool, remaining: int | None).
    Requires active plan; first unlock also needs profile-view balance.
    """
    has_plan = user_has_active_plan(viewer)
    already_unlocked = has_unlocked_profile(viewer, profile_up)
    can_view, remaining = PlanLimitService.can_view_profile(viewer)
    if has_plan and already_unlocked:
        return True, True, remaining
    if can_view:
        return True, False, remaining
    return False, already_unlocked, remaining if has_plan else 0


def get_user_plan_status(user):
    """
    Return a simple status string for the user's plan:
    - 'active'  : user has an active, non-expired plan
    - 'expired' : user has/had a plan but it is no longer active/valid
    - 'none'    : user has never purchased a plan
    """
    from .models import UserPlan

    up = _get_user_plan(user)
    if up:
        return 'active'

    if not user or not getattr(user, 'is_authenticated', False):
        return 'none'

    if UserPlan.objects.filter(user=user).exists():
        return 'expired'

    return 'none'


def is_plan_expired(user):
    """
    Return True only when the user has a plan record but it is not currently active
    (expired or deactivated). Users with no plan at all are not treated as "expired".
    """
    return get_user_plan_status(user) == 'expired'


def plan_expired_response(user=None):
    """
    Standard JSON response when a plan is required.
    Distinguishes between "no active plan" and "expired plan" for clearer UX.
    """
    status_str = get_user_plan_status(user)
    if status_str == 'expired':
        message = 'Your plan expired'
    else:
        message = 'You do not have an active plan. Please purchase a plan first.'

    return {
        'success': False,
        'error': {
            'code': 403,
            'message': message,
        },
    }


def horoscope_quota_exhausted_response():
    """403 payload when horoscope match limit is reached (distinct from no active plan)."""
    return {
        'success': False,
        'error': {
            'code': 403,
            'message': 'You have used all horoscope matches included in your plan. Upgrade or wait for renewal.',
        },
    }


class PlanLimitService:
    """
    Service to check and consume plan limits: profile view, interest, chat, contact view.
    Each can_* returns (allowed: bool, remaining: int | None).
    Consume methods decrement the usage counter when the action is performed.
    """

    @staticmethod
    def can_view_profile(user):
        """Check if user can view a full profile. Returns (can_view: bool, remaining: int | None)."""
        up = _get_user_plan(user)
        if not up:
            return False, 0
        limit = up.plan.profile_view_limit
        if limit == 0:
            return True, None
        limit = limit + (getattr(up, 'profile_view_bonus', 0) or 0)
        used = up.profile_views_used or 0
        remaining = max(0, limit - used)
        return remaining > 0, remaining

    @staticmethod
    def consume_profile_view(user):
        """Decrement profile_views_used. Call after recording a profile view."""
        up = _get_user_plan(user)
        if not up or up.plan.profile_view_limit == 0:
            return
        up.profile_views_used = (up.profile_views_used or 0) + 1
        up.save(update_fields=['profile_views_used', 'updated_at'])

    @staticmethod
    def can_send_interest(user):
        """Check if user can send interest. Returns (can_send: bool, remaining: int | None)."""
        up = _get_user_plan(user)
        if not up:
            return False, 0
        limit = up.plan.interest_limit
        if limit == 0:
            return True, None
        limit = limit + (getattr(up, 'interest_bonus', 0) or 0)
        used = up.interests_used or 0
        remaining = max(0, limit - used)
        return remaining > 0, remaining

    @staticmethod
    def consume_interest(user):
        """Decrement interests_used. Call after sending interest."""
        up = _get_user_plan(user)
        if not up or up.plan.interest_limit == 0:
            return
        up.interests_used = (up.interests_used or 0) + 1
        up.save(update_fields=['interests_used', 'updated_at'])

    @staticmethod
    def can_chat(user):
        """Check if user can initiate chat. Returns (can_chat: bool, remaining: int | None)."""
        up = _get_user_plan(user)
        if not up:
            return False, 0
        limit = up.plan.chat_limit
        if limit == 0:
            return True, None
        limit = limit + (getattr(up, 'chat_bonus', 0) or 0)
        used = up.chat_used or 0
        remaining = max(0, limit - used)
        return remaining > 0, remaining

    @staticmethod
    def consume_chat(user):
        """Decrement chat_used. Call when user starts a chat."""
        up = _get_user_plan(user)
        if not up or up.plan.chat_limit == 0:
            return
        up.chat_used = (up.chat_used or 0) + 1
        up.save(update_fields=['chat_used', 'updated_at'])

    @staticmethod
    def can_view_contact(user):
        """Check if user can view contact. Returns (can_view: bool, remaining: int | None)."""
        up = _get_user_plan(user)
        if not up:
            return False, 0
        limit = up.plan.contact_view_limit
        if limit == 0:
            return True, None
        limit = limit + (getattr(up, 'contact_view_bonus', 0) or 0)
        used = up.contact_views_used or 0
        remaining = max(0, limit - used)
        return remaining > 0, remaining

    @staticmethod
    def consume_contact_view(user):
        """Decrement contact_views_used. Call after user views a contact."""
        up = _get_user_plan(user)
        if not up or up.plan.contact_view_limit == 0:
            return
        up.contact_views_used = (up.contact_views_used or 0) + 1
        up.save(update_fields=['contact_views_used', 'updated_at'])

    @staticmethod
    def can_horoscope_match(user):
        """
        Check if user may run a compatibility / horoscope match action.
        Returns (allowed: bool, remaining: int | None). None remaining = unlimited.
        """
        up = _get_user_plan(user)
        if not up:
            return False, 0
        limit = up.plan.horoscope_match_limit
        if limit == 0:
            return True, None
        limit = limit + (getattr(up, 'horoscope_bonus', 0) or 0)
        used = up.horoscope_used or 0
        remaining = max(0, limit - used)
        return remaining > 0, remaining

    @staticmethod
    def consume_horoscope_match(user):
        """Increment horoscope_used after a successful match report. No-op if unlimited or no plan."""
        up = _get_user_plan(user)
        if not up or up.plan.horoscope_match_limit == 0:
            return
        up.horoscope_used = (up.horoscope_used or 0) + 1
        up.save(update_fields=['horoscope_used', 'updated_at'])


# Backward-compatible module-level functions (delegate to PlanLimitService)
def can_view_profile(user):
    return PlanLimitService.can_view_profile(user)


def can_send_interest(user):
    return PlanLimitService.can_send_interest(user)


def can_chat(user):
    return PlanLimitService.can_chat(user)


def can_view_contact(user):
    return PlanLimitService.can_view_contact(user)


def can_horoscope_match(user):
    return PlanLimitService.can_horoscope_match(user)


def consume_horoscope_match(user):
    return PlanLimitService.consume_horoscope_match(user)


def get_plan_info_for_response(user):
    """
    Build plan info dict for API responses: plan_id, plan_name, valid_until,
    profile_views_remaining, interests_remaining, chat_remaining,
    contact_view_remaining, horoscope_remaining.
    """
    up = _get_user_plan(user)
    if not up:
        return {
            'is_plan_active': False,
            'plan_id': None,
            'plan_name': None,
            'valid_until': None,
            'profile_views_remaining': 0,
            'interests_remaining': 0,
            'chat_remaining': 0,
        'contact_view_remaining': 0,
        'horoscope_remaining': 0,
        'service_charge_remaining': 0,
        'service_charge_paid': 0,
        }
    p = up.plan

    def _rem(limit, used, bonus=0):
        if limit == 0:
            return None  # unlimited
        return max(0, (limit + (bonus or 0)) - (used or 0))

    # Match the same logic as GET /api/v1/plans/:
    # service_charge is based on user's gender, and remaining amount is (service_charge - plan.price).
    from decimal import Decimal
    from .models import ServiceCharge

    gender = getattr(user, 'gender', None) or 'M'
    try:
        sc = ServiceCharge.objects.get(gender=gender)
        service_charge_total = sc.amount
    except ServiceCharge.DoesNotExist:
        service_charge_total = Decimal('0')

    plan_price = p.price or Decimal('0')
    service_charge_paid = _effective_service_charge_paid(up, repair_legacy=True)
    # Amount still owed on the service charge (after plan registration / partial payments).
    service_charge_remaining = max(Decimal('0'), service_charge_total - service_charge_paid)
    # Remaining registration path shown on plan cards (before first service payment).
    plan_card_remaining = max(Decimal('0'), service_charge_total - plan_price)

    return {
        'is_plan_active': True,
        'plan_id': p.id,
        'plan_name': p.name,
        'valid_until': up.valid_until.strftime('%d-%m-%Y') if up.valid_until else None,
        'profile_views_remaining': _rem(p.profile_view_limit, up.profile_views_used, getattr(up, 'profile_view_bonus', 0) or 0),
        'interests_remaining': _rem(p.interest_limit, up.interests_used, getattr(up, 'interest_bonus', 0) or 0),
        'chat_remaining': _rem(p.chat_limit, up.chat_used, getattr(up, 'chat_bonus', 0) or 0),
        'contact_view_remaining': _rem(p.contact_view_limit, up.contact_views_used, getattr(up, 'contact_view_bonus', 0) or 0),
        'horoscope_remaining': _rem(p.horoscope_match_limit, up.horoscope_used, getattr(up, 'horoscope_bonus', 0) or 0),
        'service_charge': float(service_charge_total),
        'plan_price': float(plan_price),
        'total_price': float(plan_card_remaining),
        'service_charge_remaining': float(service_charge_remaining),
        'service_charge_paid': float(service_charge_paid),
    }


def has_accepted_interest_between(user_a, user_b):
    """
    Return True if there is an accepted Interest between the two users in either direction.
    Used to gate chat until the interest request is accepted.
    """
    if not user_a or not user_b:
        return False
    if not getattr(user_a, 'is_authenticated', False) or not getattr(user_b, 'is_authenticated', False):
        return False
    from django.db.models import Q
    from .models import Interest

    return Interest.objects.filter(
        Q(sender=user_a, receiver=user_b) | Q(sender=user_b, receiver=user_a),
        status=Interest.STATUS_ACCEPTED,
    ).exists()


def interest_ui_state_from_pair_states(out_status, inc_status):
    """
    Map outgoing/incoming Interest.status (or None) to API interest_status + is_interest_sent.
    out_status: row viewer -> other; inc_status: row other -> viewer.
    """
    from .models import Interest

    if out_status == Interest.STATUS_ACCEPTED or inc_status == Interest.STATUS_ACCEPTED:
        return 'accepted', True
    if out_status:
        if out_status == Interest.STATUS_PENDING:
            return 'sent', True
        if out_status == Interest.STATUS_REJECTED:
            return 'rejected', False
        if out_status == Interest.STATUS_CANCELLED:
            return 'pending', False
    return 'pending', False


def bulk_interest_ui_states_for_viewer(viewer_id, other_user_ids):
    """
    For many profile user ids, return {other_id: (interest_status, is_interest_sent)}.
    """
    from django.db.models import Q
    from .models import Interest

    if not other_user_ids:
        return {}
    other_user_ids = list({x for x in other_user_ids})
    rows = Interest.objects.filter(
        Q(sender_id=viewer_id, receiver_id__in=other_user_ids)
        | Q(sender_id__in=other_user_ids, receiver_id=viewer_id)
    ).values_list('sender_id', 'receiver_id', 'status')
    by_other = {oid: {'out': None, 'inc': None} for oid in other_user_ids}
    for sid, rid, st in rows:
        if sid == viewer_id:
            if rid in by_other:
                by_other[rid]['out'] = st
        elif rid == viewer_id:
            if sid in by_other:
                by_other[sid]['inc'] = st
    return {
        oid: interest_ui_state_from_pair_states(d['out'], d['inc'])
        for oid, d in by_other.items()
    }


def get_interest_ui_state_for_viewer(viewer, profile_user):
    """Single-pair helper for profile preview and similar endpoints."""
    if not viewer or not profile_user:
        return 'pending', False
    m = bulk_interest_ui_states_for_viewer(viewer.pk, [profile_user.pk])
    return m.get(profile_user.pk, ('pending', False))


# --- Plan purchase & service charge (Razorpay + legacy manual) ---

PAYMENT_OPTION_PLAN_ONLY = 'plan_only'
PAYMENT_OPTION_FULL = 'full'

RAZORPAY_PURPOSE_PLAN_PURCHASE = 'plan_purchase'
RAZORPAY_PURPOSE_SERVICE_CHARGE = 'service_charge'


def get_service_charge_for_user(user) -> 'Decimal':
    from decimal import Decimal
    from .models import ServiceCharge

    gender = getattr(user, 'gender', None) or 'M'
    try:
        return ServiceCharge.objects.get(gender=gender).amount
    except ServiceCharge.DoesNotExist:
        return Decimal('0')


def compute_plan_purchase_amounts(user, plan, payment_option: str):
    """
    Return (amount_to_charge, service_charge_total, service_charge_paid_after, payment_message_prefix).
    """
    from decimal import Decimal

    service_charge_total = get_service_charge_for_user(user)
    plan_price = plan.price or Decimal('0')
    remaining_amount = max(service_charge_total - plan_price, Decimal('0'))

    if payment_option == PAYMENT_OPTION_FULL:
        return (
            remaining_amount,
            service_charge_total,
            service_charge_total,
            'Plan purchased with full payment.',
        )
    return (
        plan_price,
        service_charge_total,
        plan_price,
        'Plan purchased. Remaining service charge can be paid later.',
    )


def compute_service_charge_remaining(user):
    """Return (user_plan, remaining_decimal) or raise UserPlan.DoesNotExist."""
    from decimal import Decimal
    from .models import UserPlan

    user_plan = UserPlan.objects.select_related('plan').get(user=user, is_active=True)
    service_charge_total = user_plan.service_charge or Decimal('0')
    service_charge_paid = _effective_service_charge_paid(user_plan, repair_legacy=True)
    remaining = service_charge_total - service_charge_paid
    return user_plan, remaining


ACTIVE_SAME_PLAN = 'ACTIVE_SAME_PLAN'


class SamePlanAlreadyActiveError(Exception):
    """Raised when checkout would re-purchase the member's currently active plan."""

    def __init__(self, message: str):
        super().__init__(message)
        self.code = ACTIVE_SAME_PLAN


def resolve_current_active_user_plan(any_up, today):
    """Subscription row considered 'currently active' (same rule as plan purchase / upgrade)."""
    if not any_up or not any_up.is_active:
        return None
    if any_up.valid_until is not None and any_up.valid_until < today:
        return None
    return any_up


def same_plan_new_purchase_blocked_message(old_up, plan, *, for_staff: bool = False):
    """If the member already holds this plan as an active subscription, return a blocking message."""
    if not old_up or old_up.plan_id != plan.id:
        return None
    if for_staff:
        return f'Customer already has an active {plan.name} plan. Use renew instead.'
    return (
        f'You already have an active {plan.name} plan. '
        'Choose a different plan to upgrade, or wait until it expires.'
    )


def user_same_plan_active_preflight(user, plan):
    """
    For member checkout: return an error message if a new sale of this plan must be
    rejected (None if the purchase may proceed). activate_plan_purchase remains
    authoritative (row lock).
    """
    from .models import UserPlan

    today = timezone.now().date()
    up = UserPlan.objects.filter(user=user).select_related('plan').first()
    old_up = resolve_current_active_user_plan(up, today)
    return same_plan_new_purchase_blocked_message(old_up, plan)


def active_same_plan_error_body(message: str) -> dict:
    return {
        'success': False,
        'error': {'code': ACTIVE_SAME_PLAN, 'message': message},
    }


def activate_plan_purchase(
    *,
    user,
    plan,
    payment_option: str,
    payment_method: str,
    razorpay_payment_id: str = '',
):
    """
    Create/update UserPlan and record a successful plan-purchase Transaction.
    Returns (user_plan, txn, response_extra_dict).
    """
    from decimal import Decimal
    from django.db import transaction as db_transaction
    from django.utils import timezone

    from .models import Transaction, UserPlan

    today = timezone.now().date()
    amount_paid, service_charge_total, service_charge_paid, payment_message = (
        compute_plan_purchase_amounts(user, plan, payment_option)
    )

    with db_transaction.atomic():
        any_up = (
            UserPlan.objects
            .select_for_update()
            .select_related('plan')
            .filter(user=user)
            .first()
        )
        old_up = resolve_current_active_user_plan(any_up, today)

        blocked = same_plan_new_purchase_blocked_message(old_up, plan)
        if blocked:
            raise SamePlanAlreadyActiveError(blocked)

        plan_price = plan.price or Decimal('0')
        valid_from = today

        if old_up:
            def _remaining(plan_limit, bonus, used):
                if plan_limit == 0:
                    return 0
                effective = (plan_limit or 0) + (bonus or 0)
                return max(0, effective - (used or 0))

            carry_profile = _remaining(
                old_up.plan.profile_view_limit,
                getattr(old_up, 'profile_view_bonus', 0),
                old_up.profile_views_used,
            )
            carry_interest = _remaining(
                old_up.plan.interest_limit,
                getattr(old_up, 'interest_bonus', 0),
                old_up.interests_used,
            )
            carry_chat = _remaining(
                old_up.plan.chat_limit,
                getattr(old_up, 'chat_bonus', 0),
                old_up.chat_used,
            )
            carry_contact = _remaining(
                old_up.plan.contact_view_limit,
                getattr(old_up, 'contact_view_bonus', 0),
                old_up.contact_views_used,
            )
            carry_horo = _remaining(
                old_up.plan.horoscope_match_limit,
                getattr(old_up, 'horoscope_bonus', 0),
                old_up.horoscope_used,
            )
            valid_until = (old_up.valid_until or today) + timezone.timedelta(days=plan.duration_days)
            payment_message = 'Plan upgraded successfully with carry forward.'
        else:
            carry_profile = carry_interest = carry_chat = carry_contact = carry_horo = 0
            valid_until = valid_from + timezone.timedelta(days=plan.duration_days)

        user_plan, _ = UserPlan.objects.update_or_create(
            user=user,
            defaults={
                'plan': plan,
                'price_paid': plan_price,
                'service_charge': service_charge_total,
                'service_charge_paid': service_charge_paid,
                'valid_from': valid_from,
                'valid_until': valid_until,
                'is_active': True,
                'profile_view_bonus': carry_profile,
                'interest_bonus': carry_interest,
                'chat_bonus': carry_chat,
                'horoscope_bonus': carry_horo,
                'contact_view_bonus': carry_contact,
                'profile_views_used': 0,
                'interests_used': 0,
                'chat_used': 0,
                'horoscope_used': 0,
                'contact_views_used': 0,
            },
        )

        txn = Transaction.objects.create(
            user=user,
            plan=plan,
            amount=amount_paid,
            service_charge=service_charge_total,
            total_amount=amount_paid,
            payment_method=payment_method,
            payment_status=Transaction.STATUS_SUCCESS,
            transaction_type=Transaction.TYPE_PLAN_PURCHASE,
            transaction_id=(razorpay_payment_id or '').strip(),
        )

    service_charge_remaining = service_charge_total - service_charge_paid
    extra = {
        'message': payment_message,
        'payment_option': payment_option,
        'amount_paid': float(amount_paid),
        'service_charge_remaining': float(service_charge_remaining),
        'valid_until': valid_until.isoformat(),
        'carry_forward': {
            'profile_views': int(carry_profile),
            'interests': int(carry_interest),
            'chats': int(carry_chat),
            'contacts': int(carry_contact),
            'horoscope': int(carry_horo),
        },
    }
    try:
        from notifications.whatsapp_notify import enqueue_subscription_confirmation

        enqueue_subscription_confirmation(user, plan, amount_paid)
    except Exception:
        pass
    return user_plan, txn, extra


def pay_remaining_service_charge(
    *,
    user,
    payment_method: str,
    razorpay_payment_id: str = '',
):
    """Record payment of remaining service charge. Returns (user_plan, txn, amount_paid)."""
    from decimal import Decimal
    from django.db import transaction as db_transaction

    from .models import Transaction

    user_plan, remaining = compute_service_charge_remaining(user)
    if remaining <= 0:
        return user_plan, None, Decimal('0')

    service_charge_total = user_plan.service_charge or Decimal('0')

    with db_transaction.atomic():
        from .models import UserPlan

        user_plan = UserPlan.objects.select_for_update().get(pk=user_plan.pk)
        service_charge_paid = _effective_service_charge_paid(user_plan, repair_legacy=True)
        remaining = (user_plan.service_charge or Decimal('0')) - service_charge_paid
        if remaining <= 0:
            return user_plan, None, Decimal('0')

        txn = Transaction.objects.create(
            user=user,
            plan=user_plan.plan,
            amount=remaining,
            service_charge=remaining,
            total_amount=remaining,
            payment_method=payment_method,
            payment_status=Transaction.STATUS_SUCCESS,
            transaction_type=Transaction.TYPE_PLAN_PURCHASE,
            transaction_id=(razorpay_payment_id or '').strip(),
        )
        user_plan.service_charge_paid = service_charge_total
        user_plan.save(update_fields=['service_charge_paid', 'updated_at'])

    return user_plan, txn, remaining


def plan_purchase_response_data(txn, plan, extra: dict) -> dict:
    """Build API response payload after successful plan purchase."""
    return {
        'transaction_id': txn.id,
        'plan_name': plan.name,
        **extra,
    }
