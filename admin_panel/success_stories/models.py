from django.db import models
from django.conf import settings

from admin_panel.auth.models import AdminUser
from core.watermark import watermark_model_images


class SuccessStory(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
    )

    couple_name_1 = models.CharField(max_length=150)
    couple_name_2 = models.CharField(max_length=150)
    wedding_date = models.DateField()
    location = models.CharField(max_length=200)
    story_text = models.TextField()
    couple_photo = models.ImageField(upload_to="success_stories/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    is_featured = models.BooleanField(default=False)
    views_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        AdminUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_success_stories",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admin_success_story"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["is_featured"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.couple_name_1} & {self.couple_name_2}"

    def save(self, *args, **kwargs):
        watermark_model_images(
            self,
            watermark_path=settings.BASE_DIR / "WhatsApp Image 2026-04-24 at 4.40.09 PM.png",
        )
        super().save(*args, **kwargs)
