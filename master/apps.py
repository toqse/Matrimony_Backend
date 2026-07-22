from django.apps import AppConfig


class MasterConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'master'
    label = 'master'
    verbose_name = 'Master Data'

    def ready(self):
        # Register cache invalidation signals
        from . import signals  # noqa: F401

