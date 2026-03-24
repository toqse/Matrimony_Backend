from django.apps import AppConfig


class AdminCommissionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "admin_panel.commissions"

    def ready(self):
        from . import signals  # noqa: F401
