from django.utils import timezone
from rest_framework import serializers

from plans.models import Transaction, UserPlan


def _payment_mode_label(txn: Transaction) -> str:
    pm = (txn.payment_method or "").lower()
    tid = (txn.transaction_id or "").lower()
    if pm == Transaction.PAYMENT_UPI:
        return "UPI"
    if pm in {Transaction.PAYMENT_RAZORPAY, Transaction.PAYMENT_STRIPE}:
        if "netbank" in tid:
            return "Netbanking"
        return "Card"
    if "netbank" in tid:
        return "Netbanking"
    return "Cash"


def _status_label(txn: Transaction) -> str:
    if txn.payment_status in {Transaction.STATUS_FAILED, Transaction.STATUS_REFUNDED}:
        return "cancelled"
    up = getattr(txn.user, "user_plan", None)
    if not up:
        return "cancelled"
    today = timezone.localdate()
    if up.is_active and up.valid_until and up.valid_until >= today:
        return "active"
    return "expired"


class SubscriptionLedgerSerializer(serializers.ModelSerializer):
    customer = serializers.CharField(source="user.name", read_only=True)
    matri_id = serializers.CharField(source="user.matri_id", read_only=True)
    plan = serializers.CharField(source="plan.name", read_only=True)
    amount = serializers.DecimalField(source="total_amount", max_digits=12, decimal_places=2, read_only=True)
    payment_mode = serializers.SerializerMethodField()
    staff = serializers.SerializerMethodField()
    branch = serializers.SerializerMethodField()
    start_date = serializers.SerializerMethodField()
    expiry_date = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            "id",
            "customer",
            "matri_id",
            "plan",
            "amount",
            "payment_mode",
            "staff",
            "branch",
            "start_date",
            "expiry_date",
            "status",
        ]

    def get_payment_mode(self, obj):
        return _payment_mode_label(obj)

    def get_staff(self, obj):
        assignment = getattr(obj.user, "staff_assignment", None)
        if assignment and assignment.staff and not assignment.staff.is_deleted:
            return assignment.staff.name
        return ""

    def get_branch(self, obj):
        branch = getattr(obj.user, "branch", None)
        return getattr(branch, "name", "") if branch else ""

    def get_start_date(self, obj):
        up = getattr(obj.user, "user_plan", None)
        return up.valid_from if up else None

    def get_expiry_date(self, obj):
        up = getattr(obj.user, "user_plan", None)
        return up.valid_until if up else None

    def get_status(self, obj):
        return _status_label(obj)
