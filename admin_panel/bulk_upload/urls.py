from django.urls import path

from .views import (
    BulkUploadHistoryView,
    BulkUploadImportView,
    BulkUploadTaskStatusView,
    BulkUploadTemplateView,
    BulkUploadValidateView,
)

urlpatterns = [
    path("template/", BulkUploadTemplateView.as_view(), name="bulk-upload-template"),
    path("validate/", BulkUploadValidateView.as_view(), name="bulk-upload-validate"),
    path("import/", BulkUploadImportView.as_view(), name="bulk-upload-import"),
    path("history/", BulkUploadHistoryView.as_view(), name="bulk-upload-history"),
    path(
        "status/<str:task_id>/",
        BulkUploadTaskStatusView.as_view(),
        name="bulk-upload-status",
    ),
]
