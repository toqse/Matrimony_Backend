from decimal import Decimal

from django.conf import settings
from django.db import models

from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch
from admin_panel.staff_mgmt.models import StaffProfile
from plans.models import Plan, UserPlan


class Commission(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_PAID = "paid"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_PAID, "Paid"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    staff = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name="commissions")
    subscription = models.ForeignKey(
        UserPlan,
        on_delete=models.PROTECT,
        related_name="commissions",
        null=True,
        blank=True,
        help_text="Set when commission is tied to a user subscription; null for manual entries.",
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="commissions",
        help_text="Plan name for manual commissions when subscription is not linked.",
    )
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="commissions")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="commissions")
    sale_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    commission_amt = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    approved_by = models.ForeignKey(
        AdminUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_commissions"
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admin_commission"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["branch"]),
            models.Index(fields=["staff"]),
            models.Index(fields=["customer"]),
        ]

    def __str__(self):
        return f"{self.customer_id} - {self.staff.emp_code} - {self.commission_amt}"

    def compute_amount(self):
        self.commission_amt = (Decimal(self.sale_amount or 0) * Decimal(self.commission_rate or 0)) / Decimal("100")
