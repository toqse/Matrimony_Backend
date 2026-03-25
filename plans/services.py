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


def user_has_active_plan(user):
    """True when the user has a valid, non-expired active subscription (same as get_user_plan_status == 'active')."""
    return get_user_plan_status(user) == 'active'


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


# Backward-compatible module-level functions (delegate to PlanLimitService)
def can_view_profile(user):
    return PlanLimitService.can_view_profile(user)


def can_send_interest(user):
    return PlanLimitService.can_send_interest(user)


def can_chat(user):
    return PlanLimitService.can_chat(user)


def can_view_contact(user):
    return PlanLimitService.can_view_contact(user)


def get_plan_info_for_response(user):
    """
    Build plan info dict for API responses: plan_name, valid_until,
    profile_views_remaining, interests_remaining, chat_remaining,
    contact_view_remaining, horoscope_remaining.
    """
    up = _get_user_plan(user)
    if not up:
        return {
            'is_plan_active': False,
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
    # "Remaining" shown in UI/cards is the amount after paying plan price.
    service_charge_remaining = max(Decimal('0'), service_charge_total - plan_price)
    service_charge_paid = getattr(up, 'service_charge_paid', 0) or 0

    return {
        'is_plan_active': True,
        'plan_name': p.name,
        'valid_until': up.valid_until.isoformat() if up.valid_until else None,
        'profile_views_remaining': _rem(p.profile_view_limit, up.profile_views_used, getattr(up, 'profile_view_bonus', 0) or 0),
        'interests_remaining': _rem(p.interest_limit, up.interests_used, getattr(up, 'interest_bonus', 0) or 0),
        'chat_remaining': _rem(p.chat_limit, up.chat_used, getattr(up, 'chat_bonus', 0) or 0),
        'contact_view_remaining': _rem(p.contact_view_limit, up.contact_views_used, getattr(up, 'contact_view_bonus', 0) or 0),
        'horoscope_remaining': _rem(p.horoscope_match_limit, up.horoscope_used, getattr(up, 'horoscope_bonus', 0) or 0),
        'service_charge': float(service_charge_total),
        'plan_price': float(plan_price),
        'total_price': float(service_charge_remaining),
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
