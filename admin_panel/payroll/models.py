from django.db import models

from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch
from admin_panel.staff_mgmt.models import StaffProfile


class SalaryRecord(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_APPROVED = "approved"
    STATUS_PAID = "paid"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_PAID, "Paid"),
    ]

    staff = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name="salary_records")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="salary_records")
    month = models.DateField(help_text="First day of the payroll month, e.g. 2026-02-01")
    basic = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Sum of paid commissions in this month",
    )
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    approved_by = models.ForeignKey(
        AdminUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_salary_records"
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admin_salary_record"
        ordering = ["-month", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["staff", "month"], name="uniq_salary_staff_month"),
        ]
        indexes = [
            models.Index(fields=["month"]),
            models.Index(fields=["status"]),
            models.Index(fields=["branch"]),
        ]

    def __str__(self) -> str:
        return f"{self.staff.emp_code} {self.month} {self.status}"
