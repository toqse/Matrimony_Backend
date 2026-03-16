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

    def _rem(limit, used):
        if limit == 0:
            return None  # unlimited
        return max(0, limit - (used or 0))

    service_charge_total = up.service_charge or 0
    service_charge_paid = getattr(up, 'service_charge_paid', 0) or 0
    service_charge_remaining = max(0, service_charge_total - service_charge_paid)

    return {
        'is_plan_active': True,
        'plan_name': p.name,
        'valid_until': up.valid_until.isoformat() if up.valid_until else None,
        'profile_views_remaining': _rem(p.profile_view_limit, up.profile_views_used),
        'interests_remaining': _rem(p.interest_limit, up.interests_used),
        'chat_remaining': _rem(p.chat_limit, up.chat_used),
        'contact_view_remaining': _rem(p.contact_view_limit, up.contact_views_used),
        'horoscope_remaining': _rem(p.horoscope_match_limit, up.horoscope_used),
        'service_charge_remaining': float(service_charge_remaining),
        'service_charge_paid': float(service_charge_paid),
    }
