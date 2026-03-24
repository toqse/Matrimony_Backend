from django.db import models

from admin_panel.auth.models import AdminUser
from plans.models import Transaction


class PaymentReview(models.Model):
    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE, related_name="payment_review")
    reviewed_by = models.ForeignKey(
        AdminUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_reviews",
    )
    rejection_reason = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admin_payment_review"
        ordering = ["-created_at"]
