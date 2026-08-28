from django.db import models

from admin_panel.auth.models import AdminUser


class Testimonial(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
    )

    name = models.CharField(max_length=150)
    role = models.CharField(max_length=150)
    review = models.TextField()
    rating = models.PositiveSmallIntegerField(default=5)
    avatar = models.ImageField(upload_to="testimonials/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    sort_order = models.IntegerField(default=0)
    created_by = models.ForeignKey(
        AdminUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_testimonials",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admin_testimonial"
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["sort_order"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return self.name
