from django.apps import AppConfig


class AppConfigConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "admin_panel.app_config"
    label = "admin_app_config"
