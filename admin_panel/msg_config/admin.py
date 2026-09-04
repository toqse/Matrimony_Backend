from django.contrib import admin

from .models import MsgConfig


@admin.register(MsgConfig)
class MsgConfigAdmin(admin.ModelAdmin):
    """Django superuser control for MSG91 Development Mode and related settings."""

    list_display = (
        "development_mode",
        "integrated_number",
        "auth_key_configured",
        "updated_at",
    )
    list_display_links = ("development_mode",)
    fields = (
        "development_mode",
        "auth_key",
        "integrated_number",
        "namespace",
        "updated_at",
    )
    readonly_fields = ("updated_at",)

    def auth_key_configured(self, obj):
        return bool((obj.auth_key or "").strip() or obj.resolve_auth_key())

    auth_key_configured.boolean = True
    auth_key_configured.short_description = "Auth key set"

    def has_add_permission(self, request):
        # Singleton: only one row (pk=1)
        if MsgConfig.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Jump straight to the singleton edit form when it exists
        MsgConfig.load()
        return super().changelist_view(request, extra_context=extra_context)
