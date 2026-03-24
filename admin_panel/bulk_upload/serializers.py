from rest_framework import serializers

from .models import BulkUploadJob


class BulkUploadImportRequestSerializer(serializers.Serializer):
    validation_token = serializers.CharField(required=True)
    branch_id = serializers.IntegerField(required=False, allow_null=True)


class BulkUploadJobHistorySerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = BulkUploadJob
        fields = [
            "id",
            "uploaded_by_name",
            "branch_name",
            "file_name",
            "file_format",
            "total_rows",
            "valid_rows",
            "error_rows",
            "imported_count",
            "status",
            "validation_token",
            "task_id",
            "error_details",
            "created_at",
            "completed_at",
        ]
