from django.db import models
from django.db.models import Q

class Branch(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    city = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                condition=Q(is_deleted=False),
                name="uniq_branch_name_not_deleted",
            ),
            models.UniqueConstraint(
                fields=["code"],
                condition=Q(is_deleted=False),
                name="uniq_branch_code_not_deleted",
            ),
            models.UniqueConstraint(
                fields=["email"],
                condition=Q(is_deleted=False),
                name="uniq_branch_email_not_deleted",
            ),
        ]

    def __str__(self):
        return self.name