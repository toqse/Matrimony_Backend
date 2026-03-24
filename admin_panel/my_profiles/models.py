from django.db import models


class EmailTemplate(models.Model):
    """Branch Manager — send templated email to a profile (My Profiles)."""

    name = models.CharField(max_length=200)
    subject = models.CharField(max_length=500)
    body_text = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admin_my_profiles_email_template"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
