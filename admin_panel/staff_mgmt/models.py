import re

from django.db import models
from django.conf import settings

from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch
from core.watermark import watermark_model_images


def _next_emp_code() -> str:
    last = StaffProfile.objects.order_by("-id").values_list("emp_code", flat=True).first()
    if not last:
        return "EMP001"
    m = re.search(r"(\d+)$", last or "")
    num = int(m.group(1)) if m else 0
    return f"EMP{num + 1:03d}"


class StaffProfile(models.Model):
    admin_user = models.OneToOneField(
        AdminUser, on_delete=models.CASCADE, related_name="staff_profile"
    )
    emp_code = models.CharField(max_length=20, unique=True, db_index=True)

    # Personal
    name = models.CharField(max_length=150)
    mobile = models.CharField(max_length=10, unique=True, db_index=True)
    email = models.EmailField(null=True, blank=True, unique=True)
    profile_photo = models.ImageField(upload_to="staff/photos/", null=True, blank=True)

    # Employment
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="staff_members")
    designation = models.CharField(max_length=120)
    department = models.CharField(max_length=120, blank=True)
    joining_date = models.DateField(null=True, blank=True)
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    monthly_target = models.PositiveIntegerField(default=1)
    achieved_target = models.PositiveIntegerField(default=0)
    pf_number = models.CharField(max_length=50, blank=True)
    esi_number = models.CharField(max_length=50, blank=True)

    # Address
    street_address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=10, blank=True)

    # Bank and login
    bank_name = models.CharField(max_length=150, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    ifsc_code = models.CharField(max_length=20, blank=True)
    upi_id = models.CharField(max_length=120, blank=True)
    login_username = models.CharField(max_length=150, blank=True, unique=True, null=True)
    login_password_hash = models.CharField(max_length=255, blank=True)

    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admin_staff_profile"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.emp_code:
            self.emp_code = _next_emp_code()
        watermark_model_images(
            self,
            watermark_path=settings.BASE_DIR / "WhatsApp Image 2026-04-24 at 4.40.09 PM.png",
        )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.emp_code} - {self.name}"
