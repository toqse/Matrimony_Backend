from django.db import models
from django.utils import timezone

from master.models import Branch


class AdminUser(models.Model):
    ROLE_ADMIN = "admin"
    ROLE_BRANCH_MANAGER = "branch_manager"
    ROLE_STAFF = "staff"

    ROLE_CHOICES = (
        (ROLE_ADMIN, "Admin"),
        (ROLE_BRANCH_MANAGER, "Branch Manager"),
        (ROLE_STAFF, "Staff"),
    )

    mobile = models.CharField(max_length=15, unique=True)
    email = models.EmailField(blank=True, default="")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    name = models.CharField(max_length=150)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(null=True, blank=True)
    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_expiry = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admin_admin_user"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.mobile})"

    @property
    def is_authenticated(self) -> bool:
        # Needed so DRF's IsAuthenticated works with this model instance.
        return True

