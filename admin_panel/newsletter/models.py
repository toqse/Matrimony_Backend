from django.db import models


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True, db_index=True)
    source = models.CharField(max_length=50, default="footer")
    is_active = models.BooleanField(default=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "newsletter_subscriber"
        ordering = ["-subscribed_at"]

    def __str__(self):
        return self.email
