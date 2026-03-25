from __future__ import annotations

from django.urls import reverse
from rest_framework import serializers

from admin_panel.payroll.models import SalaryRecord


class StaffSalaryHistorySerializer(serializers.ModelSerializer):
    month = serializers.SerializerMethodField()
    year = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = SalaryRecord
        fields = [
            "id",
            "month",
            "year",
            "basic",
            "commission",
            "allowances",
            "deductions",
            "gross",
            "net",
            "status",
            "download_url",
        ]

    def get_month(self, obj: SalaryRecord) -> str:
        if not obj.month:
            return ""
        return obj.month.strftime("%B")

    def get_year(self, obj: SalaryRecord) -> int:
        if not obj.month:
            return 0
        return obj.month.year

    def get_download_url(self, obj: SalaryRecord) -> str:
        request = self.context.get("request")
        if not request:
            return ""
        path = reverse("staff-salary-download", kwargs={"pk": obj.pk})
        return request.build_absolute_uri(path)
