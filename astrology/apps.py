from django.apps import AppConfig


class AstrologyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'astrology'
    label = 'astrology'
    verbose_name = 'Astrology'

    def ready(self):
        from . import signals  # noqa: F401
