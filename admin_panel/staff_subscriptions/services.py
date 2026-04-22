"""Staff-scoped subscription queryset, KPIs, and plan sale / renew helpers."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from admin_panel.subscriptions.models import CustomerStaffAssignment
from admin_panel.subscriptions.serializers import _status_label
from admin_panel.staff_mgmt.models import StaffProfile
from plans.models import Plan, ServiceCharge, Transaction, UserPlan


VALID_STATUS = frozenset({"active", "expired", "cancelled"})


def resolve_current_active_user_plan(any_up: UserPlan | None, today) -> UserPlan | None:
    """Subscription row considered 'currently active' (same rule as plan purchase / upgrade)."""
    if not any_up or not any_up.is_active:
        return None
    if any_up.valid_until is not None and any_up.valid_until < today:
        return None
    return any_up


def same_plan_new_purchase_blocked_message(old_up: UserPlan | None, plan: Plan) -> str | None:
    """If customer already holds this plan as an active subscription, return a blocking message."""
    if old_up and old_up.plan_id == plan.id:
        return f"Customer already has an active {plan.name} plan. Use renew instead."
    return None


def staff_subscription_same_plan_active_preflight(customer: User, plan: Plan) -> str | None:
    """
    For POST /api/v1/staff/subscriptions/: return an error message if a new sale of this plan
    must be rejected (None if the purchase may proceed). Uses the same rules as
    record_staff_plan_purchase (without row locks — record remains authoritative).
    """
    today = timezone.now().date()
    up = UserPlan.objects.filter(user=customer).select_related("plan").first()
    old_up = resolve_current_active_user_plan(up, today)
    return same_plan_new_purchase_blocked_message(old_up, plan)
STAFF_PAYMENT_MODES = frozenset({"cash", "upi", "card", "netbanking"})


def staff_subscription_transactions(staff: StaffProfile):
    return (
        Transaction.objects.filter(
            transaction_type=Transaction.TYPE_PLAN_PURCHASE,
            user__staff_assignment__staff=staff,
        )
        .select_related("user", "user__branch", "user__user_plan", "plan", "user__staff_assignment", "user__staff_assignment__staff")
        .order_by("-created_at")
    )


def map_staff_payment_to_txn(payment_mode: str, payment_reference: str) -> tuple[str, str]:
    ref = (payment_reference or "").strip()
    if payment_mode == "cash":
        return Transaction.PAYMENT_MANUAL, ref
    if payment_mode == "upi":
        return Transaction.PAYMENT_UPI, ref
    if payment_mode == "card":
        return Transaction.PAYMENT_STRIPE, ref
    if payment_mode == "netbanking":
        return Transaction.PAYMENT_STRIPE, (f"{ref} netbank" if ref else "netbank")
    return Transaction.PAYMENT_MANUAL, ref


def apply_staff_subscription_filters(qs, request):
    """Returns (queryset | None, Response | None)."""
    from rest_framework import status
    from rest_framework.response import Response

    search = (request.query_params.get("search") or "").strip()
    if search:
        qs = qs.filter(
            Q(user__name__icontains=search) | Q(user__matri_id__icontains=search)
        )

    status_filter = (request.query_params.get("status") or "").strip().lower()
    if status_filter:
        if status_filter not in VALID_STATUS:
            return None, Response(
                {
                    "success": False,
                    "error": {
                        "code": 400,
                        "message": "Invalid status. Must be: active, expired, cancelled.",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        today = timezone.localdate()
        if status_filter == "active":
            qs = qs.filter(
                payment_status=Transaction.STATUS_SUCCESS,
                user__user_plan__is_active=True,
                user__user_plan__valid_until__gte=today,
            )
        elif status_filter == "expired":
            qs = qs.filter(payment_status=Transaction.STATUS_SUCCESS).filter(
                Q(user__user_plan__is_active=False)
                | Q(user__user_plan__valid_until__lt=today)
            )
        elif status_filter == "cancelled":
            qs = qs.filter(
                payment_status__in=[
                    Transaction.STATUS_FAILED,
                    Transaction.STATUS_REFUNDED,
                ]
            )

    return qs, None


def build_staff_subscription_summary(staff: StaffProfile) -> dict:
    qs = staff_subscription_transactions(staff).filter(
        payment_status=Transaction.STATUS_SUCCESS
    )
    total_sold = 0
    active = 0
    expired = 0
    revenue_dec = Decimal("0")

    for txn in qs.iterator(chunk_size=300):
        total_sold += 1
        revenue_dec += Decimal(txn.total_amount or 0)
        label = _status_label(txn)
        if label == "active":
            active += 1
        elif label == "expired":
            expired += 1

    return {
        "total_sold": total_sold,
        "active": active,
        "expired": expired,
        "revenue": int(revenue_dec),
    }


def ensure_staff_owns_customer(staff: StaffProfile, customer: User):
    from rest_framework import status
    from rest_framework.response import Response

    assignment = CustomerStaffAssignment.objects.filter(user=customer).first()
    if assignment and assignment.staff_id != staff.pk:
        return Response(
            {
                "success": False,
                "error": {
                    "code": 403,
                    "message": "This customer is assigned to another staff member.",
                },
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    CustomerStaffAssignment.objects.update_or_create(
        user=customer,
        defaults={"staff": staff},
    )
    return None


def record_staff_plan_purchase(
    *,
    customer: User,
    plan: Plan,
    payment_mode: str,
    payment_reference: str,
    amount: Decimal,
) -> Transaction:
    """
    plan_only-style purchase: customer pays plan.price now; service_charge tracked, not fully paid.
    Caller must call ensure_staff_owns_customer before this (same atomic boundary is optional).
    Raises ValueError with message string for 400 responses.
    """
    from django.db import transaction as db_transaction

    plan_price = plan.price or Decimal("0")
    if amount <= Decimal("0") or amount > plan_price:
        raise ValueError(
            f"Amount must be greater than zero and at most plan price (₹{plan_price})."
        )

    today = timezone.now().date()
    pm, tid = map_staff_payment_to_txn(payment_mode, payment_reference)

    gender = getattr(customer, "gender", None) or "M"
    try:
        sc = ServiceCharge.objects.get(gender=gender)
        service_charge_total = sc.amount
    except ServiceCharge.DoesNotExist:
        service_charge_total = Decimal("0")

    amount_paid = amount
    service_charge_paid = Decimal("0")

    with db_transaction.atomic():
        any_up = (
            UserPlan.objects.select_for_update()
            .select_related("plan")
            .filter(user=customer)
            .first()
        )
        old_up = resolve_current_active_user_plan(any_up, today)

        blocked = same_plan_new_purchase_blocked_message(old_up, plan)
        if blocked:
            raise ValueError(blocked)

        if old_up:
            def _remaining(plan_limit, bonus, used):
                if plan_limit == 0:
                    return 0
                effective = (plan_limit or 0) + (bonus or 0)
                return max(0, effective - (used or 0))

            carry_profile = _remaining(
                old_up.plan.profile_view_limit,
                getattr(old_up, "profile_view_bonus", 0),
                old_up.profile_views_used,
            )
            carry_interest = _remaining(
                old_up.plan.interest_limit,
                getattr(old_up, "interest_bonus", 0),
                old_up.interests_used,
            )
            carry_chat = _remaining(
                old_up.plan.chat_limit,
                getattr(old_up, "chat_bonus", 0),
                old_up.chat_used,
            )
            carry_contact = _remaining(
                old_up.plan.contact_view_limit,
                getattr(old_up, "contact_view_bonus", 0),
                old_up.contact_views_used,
            )
            carry_horo = _remaining(
                old_up.plan.horoscope_match_limit,
                getattr(old_up, "horoscope_bonus", 0),
                old_up.horoscope_used,
            )

            valid_from = today
            valid_until = (old_up.valid_until or today) + timedelta(
                days=plan.duration_days
            )
        else:
            carry_profile = 0
            carry_interest = 0
            carry_chat = 0
            carry_contact = 0
            carry_horo = 0
            valid_from = today
            valid_until = valid_from + timedelta(days=plan.duration_days)

        UserPlan.objects.update_or_create(
            user=customer,
            defaults={
                "plan": plan,
                "price_paid": amount_paid,
                "service_charge": service_charge_total,
                "service_charge_paid": service_charge_paid,
                "valid_from": valid_from,
                "valid_until": valid_until,
                "is_active": True,
                "profile_view_bonus": carry_profile,
                "interest_bonus": carry_interest,
                "chat_bonus": carry_chat,
                "horoscope_bonus": carry_horo,
                "contact_view_bonus": carry_contact,
                "profile_views_used": 0,
                "interests_used": 0,
                "chat_used": 0,
                "horoscope_used": 0,
                "contact_views_used": 0,
            },
        )

        txn = Transaction.objects.create(
            user=customer,
            plan=plan,
            amount=amount_paid,
            service_charge=service_charge_total,
            total_amount=amount_paid,
            payment_method=pm,
            payment_status=Transaction.STATUS_SUCCESS,
            transaction_type=Transaction.TYPE_PLAN_PURCHASE,
            transaction_id=tid,
        )

    return txn


def renew_staff_plan(
    *,
    ledger_txn: Transaction,
    payment_mode: str,
    payment_reference: str,
    amount: Decimal,
) -> Transaction:
    """
    Extend UserPlan validity for the plan linked to ledger_txn; records a new successful transaction.
    Caller must call ensure_staff_owns_customer for ledger_txn.user before this.
    """
    from django.db import transaction as db_transaction

    plan = ledger_txn.plan
    if not plan:
        raise ValueError("Invalid subscription record.")

    plan_price = plan.price or Decimal("0")
    if amount != plan_price:
        raise ValueError(f"Amount must equal plan price (₹{plan_price}).")

    customer = ledger_txn.user
    today = timezone.localdate()
    pm, tid = map_staff_payment_to_txn(payment_mode, payment_reference)

    gender = getattr(customer, "gender", None) or "M"
    try:
        sc = ServiceCharge.objects.get(gender=gender)
        service_charge_total = sc.amount
    except ServiceCharge.DoesNotExist:
        service_charge_total = Decimal("0")

    with db_transaction.atomic():
        up = (
            UserPlan.objects.select_for_update()
            .select_related("plan")
            .filter(user=customer)
            .first()
        )
        if not up or up.plan_id != plan.id:
            raise ValueError(
                "Renew is only available for the customer's current plan on file."
            )

        if up.valid_until and up.valid_until >= today:
            new_until = up.valid_until + timedelta(days=plan.duration_days)
        else:
            new_until = today + timedelta(days=plan.duration_days)

        up.valid_until = new_until
        up.is_active = True
        up.valid_from = up.valid_from or today
        up.save(
            update_fields=[
                "valid_until",
                "is_active",
                "valid_from",
                "updated_at",
            ]
        )

        txn = Transaction.objects.create(
            user=customer,
            plan=plan,
            amount=amount,
            service_charge=service_charge_total,
            total_amount=amount,
            payment_method=pm,
            payment_status=Transaction.STATUS_SUCCESS,
            transaction_type=Transaction.TYPE_PLAN_PURCHASE,
            transaction_id=tid,
        )

    return txn


def export_apply_filters(qs, request):
    """Optional status + date range on created_at for export."""
    from datetime import datetime

    from rest_framework import status
    from rest_framework.response import Response

    qs, err = apply_staff_subscription_filters(qs, request)
    if err:
        return None, err

    start_s = (request.query_params.get("start") or "").strip()
    end_s = (request.query_params.get("end") or "").strip()

    def _parse(d: str):
        try:
            return datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            return None

    if start_s:
        start_d = _parse(start_s)
        if not start_d:
            return None, Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Invalid start date. Use YYYY-MM-DD."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = qs.filter(created_at__date__gte=start_d)
    if end_s:
        end_d = _parse(end_s)
        if not end_d:
            return None, Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Invalid end date. Use YYYY-MM-DD."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = qs.filter(created_at__date__lte=end_d)

    return qs, None


def first_serializer_error(serializer) -> str:
    for err in serializer.errors.values():
        if isinstance(err, list) and err:
            return str(err[0])
        if isinstance(err, dict):
            for v in err.values():
                if isinstance(v, list) and v:
                    return str(v[0])
        return str(err)
    return "Invalid request."
