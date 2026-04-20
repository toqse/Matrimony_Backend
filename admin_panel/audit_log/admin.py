from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "actor_name",
        "actor_role",
        "action",
        "resource",
        "ip_address",
    )
    list_filter = ("action", "actor_role", "role", "created_at")
    search_fields = ("actor_name", "resource", "details", "ip_address")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = (
        "created_at",
        "updated_at",
        "actor",
        "actor_name",
        "actor_role",
        "role",
        "action",
        "resource",
        "details",
        "old_value",
        "new_value",
        "ip_address",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return True
