from django.db import models

from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch
from plans.models import Plan, Transaction


class PaymentReceiptSequence(models.Model):
    """Per-calendar-year counter for RCP-YYYY-NNN (locked under select_for_update)."""

    year = models.PositiveIntegerField(unique=True, db_index=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "admin_staff_payment_receipt_seq"


class PaymentEntry(models.Model):
    MODE_CASH = "cash"
    MODE_GPAY_UPI = "gpay_upi"
    MODE_CHOICES = [
        (MODE_CASH, "Cash"),
        (MODE_GPAY_UPI, "GPay/UPI"),
    ]

    STATUS_PENDING = "pending"
    STATUS_VERIFIED = "verified"
    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_COMPLETED, "Completed"),
    ]

    receipt_id = models.CharField(max_length=30, unique=True, db_index=True)
    staff = models.ForeignKey(
        AdminUser,
        on_delete=models.CASCADE,
        related_name="staff_payment_entries",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="staff_payment_entries",
    )
    customer_matri = models.CharField(max_length=20, db_index=True)
    customer_name = models.CharField(max_length=100)
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="staff_payment_entries",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    reference_no = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        AdminUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verified_payments",
    )
    transaction = models.OneToOneField(
        Transaction,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="staff_payment_entry",
    )

    class Meta:
        db_table = "admin_staff_payment_entry"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["staff", "-created_at"]),
            models.Index(fields=["branch", "-created_at"]),
        ]

    def __str__(self) -> str:
        return self.receipt_id
