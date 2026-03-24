from django.urls import path

from .views import AuditLogActionOptionsAPIView, AuditLogListAPIView

urlpatterns = [
    path("", AuditLogListAPIView.as_view(), name="admin-audit-log-list"),
    path("actions/", AuditLogActionOptionsAPIView.as_view(), name="admin-audit-log-actions"),
]
