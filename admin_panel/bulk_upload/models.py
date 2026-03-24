from django.db import models
from django.utils import timezone

from admin_panel.auth.models import AdminUser
from master.models import Branch


class BulkUploadJob(models.Model):
    STATUS_VALIDATED = "validated"
    STATUS_QUEUED = "queued"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_VALIDATED, "Validated"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    uploaded_by = models.ForeignKey(AdminUser, on_delete=models.PROTECT, related_name="bulk_upload_jobs")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="bulk_upload_jobs")
    file_name = models.CharField(max_length=255)
    file_format = models.CharField(max_length=10)
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    imported_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_VALIDATED)
    validation_token = models.CharField(max_length=128, unique=True, db_index=True)
    task_id = models.CharField(max_length=64, blank=True, db_index=True)
    error_details = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "admin_bulk_upload_job"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["uploaded_by"]),
            models.Index(fields=["branch"]),
        ]

    def mark_processing(self):
        self.status = self.STATUS_PROCESSING
        self.save(update_fields=["status"])

    def mark_completed(self, imported_count: int, errors: list[dict]):
        self.status = self.STATUS_COMPLETED
        self.imported_count = imported_count
        self.error_details = errors
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "imported_count", "error_details", "completed_at"])

    def mark_failed(self, message: str):
        self.status = self.STATUS_FAILED
        self.error_details = [{"row": None, "field": "non_field_error", "message": message}]
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "error_details", "completed_at"])
