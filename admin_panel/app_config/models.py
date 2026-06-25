from django.db import models


class MobileAppConfig(models.Model):
    id = models.PositiveSmallIntegerField(
        primary_key=True,
        default=1,
        editable=False,
        db_column="singleton_id",
    )
    android_version = models.CharField(max_length=32, default="1.0.0")
    ios_version = models.CharField(max_length=32, default="1.0.0")
    android_force_update = models.BooleanField(default=False)
    ios_force_update = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mobile_app_config"
        verbose_name = "Mobile app config"

    def __str__(self):
        return f"MobileAppConfig(android={self.android_version}, ios={self.ios_version})"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
