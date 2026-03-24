from rest_framework import serializers

from plans.models import Transaction


def payment_mode_label(obj):
    if obj.payment_method == Transaction.PAYMENT_MANUAL:
        return "cash"
    if obj.payment_method == Transaction.PAYMENT_UPI:
        return "upi"
    tx = (obj.transaction_id or "").lower()
    if "netbank" in tx or "bank" in tx:
        return "netbanking"
    return "card"


def payment_status_label(obj):
    if obj.payment_status == Transaction.STATUS_SUCCESS:
        return "verified"
    if obj.payment_status == Transaction.STATUS_PENDING:
        return "pending"
    return "rejected"


class PaymentTableSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    date = serializers.SerializerMethodField()
    time = serializers.SerializerMethodField()
    receipt_txn_id = serializers.SerializerMethodField()
    customer_name = serializers.CharField(source="user.name", read_only=True)
    matri_id = serializers.CharField(source="user.matri_id", read_only=True)
    plan = serializers.SerializerMethodField()
    amount = serializers.DecimalField(source="total_amount", max_digits=12, decimal_places=2, read_only=True)
    mode = serializers.SerializerMethodField()
    branch = serializers.SerializerMethodField()
    staff = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    def get_date(self, obj):
        return obj.created_at.strftime("%Y-%m-%d")

    def get_time(self, obj):
        return obj.created_at.strftime("%I:%M %p")

    def get_receipt_txn_id(self, obj):
        return obj.transaction_id or f"PAY-{obj.id:06d}"

    def get_plan(self, obj):
        return obj.plan.name if obj.plan_id else ""

    def get_mode(self, obj):
        return payment_mode_label(obj)

    def get_branch(self, obj):
        return obj.user.branch.name if getattr(obj.user, "branch", None) else ""

    def get_staff(self, obj):
        asn = getattr(obj.user, "staff_assignment", None)
        return asn.staff.name if asn and asn.staff else ""

    def get_status(self, obj):
        return payment_status_label(obj)


class PaymentDetailSerializer(PaymentTableSerializer):
    rejection_reason = serializers.SerializerMethodField()
    payment_method = serializers.CharField(read_only=True)
    payment_status = serializers.CharField(read_only=True)
    transaction_type = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    def get_rejection_reason(self, obj):
        review = getattr(obj, "payment_review", None)
        return review.rejection_reason if review else ""
