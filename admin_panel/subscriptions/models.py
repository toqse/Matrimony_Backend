from django.conf import settings
from django.db import models

from admin_panel.staff_mgmt.models import StaffProfile


class CustomerStaffAssignment(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_assignment",
    )
    staff = models.ForeignKey(
        StaffProfile,
        on_delete=models.CASCADE,
        related_name="assigned_customers",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "admin_customer_staff_assignment"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.staff.emp_code}"
