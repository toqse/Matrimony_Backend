import csv
import io

from celery.result import AsyncResult
from django.http import HttpResponse
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from master.models import Branch as MasterBranch

from matrimony_backend.celery import app as celery_app

from .legacy_runner import (
    LEGACY_ASYNC_ROW_THRESHOLD,
    cache_legacy_payload,
    decode_uploaded_csv,
    get_cached_legacy_payload,
    import_legacy_csv_text,
    validate_legacy_csv_text,
)
from .models import BulkUploadJob
from .parser import TEMPLATE_COLUMNS, is_legacy_format, parse_upload_file, read_upload_file_text
from .permissions import IsAdminOrBranchManager
from .serializers import BulkUploadJobHistorySerializer
from .tasks import bulk_import_legacy_profiles_task, bulk_import_profiles_task, run_import_job
from .template_assets import load_bulk_upload_template_xlsx
from .validators import (
    ASYNC_ROW_THRESHOLD,
    cache_validation_payload,
    get_cached_payload,
    validate_rows,
)


def _resolve_branch_id(request, body_branch_id):
    user = request.user
    if getattr(user, "role", None) == AdminUser.ROLE_BRANCH_MANAGER:
        return getattr(user, "branch_id", None)
    if body_branch_id is not None:
        return body_branch_id
    return getattr(user, "branch_id", None)


class BulkUploadTemplateView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminOrBranchManager]

    def get(self, request):
        fmt = (request.query_params.get("format") or "csv").strip().lower()
        if fmt not in ("csv", "xlsx"):
            return Response(
                {"success": False, "error": {"message": "format must be csv or xlsx"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(TEMPLATE_COLUMNS)
            response = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = (
                'attachment; filename="bulk_upload_template.csv"'
            )
            return response

        content, filename = load_bulk_upload_template_xlsx()
        response = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class BulkUploadValidateView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminOrBranchManager]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        f = request.FILES.get("file")
        if not f:
            return Response(
                {"success": False, "error": {"message": "file is required"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        name = (getattr(f, "name", "") or "").lower()
        if not (name.endswith(".csv") or name.endswith(".xlsx")):
            return Response(
                {
                    "success": False,
                    "error": {"message": "Only .csv and .xlsx files are accepted"},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Sniff the headers up-front so we can route legacy matrimony exports
        # (with `horochart`/`mother toungue`/etc.) through the legacy importer
        # instead of failing the strict header check.
        csv_text, headers = read_upload_file_text(f)
        if is_legacy_format(headers):
            return self._validate_legacy(request, f, name, csv_text)

        # Reset stream so the strict path can still call .read() the way it
        # always has done (parse_upload_file consumes the file object).
        f.seek(0)
        try:
            _, data_rows = parse_upload_file(f)
        except ValueError as exc:
            return Response(
                {
                    "success": False,
                    "error": {
                        "message": str(exc),
                        "details": [{"row": 1, "field": "headers", "message": str(exc)}],
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        total_rows, valid_rows, error_rows, errors, valid_payloads = validate_rows(data_rows)
        job = BulkUploadJob.objects.create(
            uploaded_by=request.user,
            branch_id=getattr(request.user, "branch_id", None) if getattr(request.user, "role", None) == AdminUser.ROLE_BRANCH_MANAGER else None,
            file_name=getattr(f, "name", "") or "upload",
            file_format="xlsx" if name.endswith(".xlsx") else "csv",
            total_rows=total_rows,
            valid_rows=valid_rows,
            error_rows=error_rows,
            imported_count=0,
            status=BulkUploadJob.STATUS_VALIDATED,
            validation_token="pending",
            error_details=errors,
        )
        validation_token = cache_validation_payload(request.user.pk, job.id, valid_payloads)
        job.validation_token = validation_token
        job.save(update_fields=["validation_token"])

        return Response(
            {
                "success": True,
                "data": {
                    "job_id": job.id,
                    "total_rows": total_rows,
                    "valid_rows": valid_rows,
                    "error_rows": error_rows,
                    "errors": errors,
                    "validation_token": validation_token,
                },
            }
        )

    def _validate_legacy(self, request, uploaded_file, name: str, csv_text: str):
        """Validate a legacy matrimony CSV via LegacyImporter dry-run.

        Caches the raw CSV text so the import phase can run the importer
        for real without needing the original file again.
        """
        result = validate_legacy_csv_text(csv_text)
        job = BulkUploadJob.objects.create(
            uploaded_by=request.user,
            branch_id=getattr(request.user, "branch_id", None)
            if getattr(request.user, "role", None) == AdminUser.ROLE_BRANCH_MANAGER
            else None,
            file_name=getattr(uploaded_file, "name", "") or "upload",
            file_format="xlsx" if name.endswith(".xlsx") else "csv",
            total_rows=result["total_rows"],
            valid_rows=result["valid_rows"],
            error_rows=result["error_rows"],
            imported_count=0,
            status=BulkUploadJob.STATUS_VALIDATED,
            validation_token="pending",
            error_details=result["errors"],
        )
        validation_token = cache_legacy_payload(
            {
                "admin_user_id": int(request.user.pk),
                "job_id": int(job.id),
                "csv_text": csv_text,
                "legacy": True,
                "errors": result["errors"],
                "valid_rows": result["valid_rows"],
                "error_rows": result["error_rows"],
                "total_rows": result["total_rows"],
            }
        )
        job.validation_token = validation_token
        job.save(update_fields=["validation_token"])

        return Response(
            {
                "success": True,
                "data": {
                    "job_id": job.id,
                    "total_rows": result["total_rows"],
                    "valid_rows": result["valid_rows"],
                    "error_rows": result["error_rows"],
                    "errors": result["errors"],
                    "validation_token": validation_token,
                    "legacy": True,
                },
            }
        )


class BulkUploadImportView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminOrBranchManager]
    parser_classes = [JSONParser]

    def post(self, request):
        token = (request.data.get("validation_token") or "").strip()
        if not token:
            return Response(
                {"success": False, "error": {"message": "validation_token is required"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        branch_raw = request.data.get("branch_id")
        body_branch_id = None
        if branch_raw is not None and branch_raw != "":
            try:
                body_branch_id = int(branch_raw)
            except (TypeError, ValueError):
                return Response(
                    {"success": False, "error": {"message": "Invalid branch_id"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not MasterBranch.objects.filter(pk=body_branch_id, is_active=True).exists():
                return Response(
                    {"success": False, "error": {"message": "Branch not found"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        branch_id = _resolve_branch_id(request, body_branch_id)

        # Legacy CSVs use a separate cache namespace and a different runner.
        legacy_cached = get_cached_legacy_payload(token)
        if legacy_cached:
            return self._import_legacy(request, token, legacy_cached, branch_id)

        cached = get_cached_payload(token)
        if not cached:
            return Response(
                {
                    "success": False,
                    "error": {"message": "Invalid or expired validation token"},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        row_count = len(cached.get("rows") or [])
        job_id = int(cached.get("job_id"))
        job = BulkUploadJob.objects.filter(pk=job_id).first()
        if not job:
            return Response(
                {"success": False, "error": {"message": "Bulk upload job not found"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if int(job.uploaded_by_id) != int(request.user.pk):
            return Response(
                {"success": False, "error": {"message": "Access denied"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        if branch_id is not None and job.branch_id != branch_id:
            job.branch_id = branch_id
            job.save(update_fields=["branch"])

        if row_count > ASYNC_ROW_THRESHOLD:
            async_result = bulk_import_profiles_task.delay(job_id, token, request.user.pk, branch_id)
            job.status = BulkUploadJob.STATUS_QUEUED
            job.task_id = async_result.id
            job.save(update_fields=["status", "task_id"])
            return Response(
                {
                    "success": True,
                    "data": {
                        "job_id": job.id,
                        "async": True,
                        "task_id": async_result.id,
                        "queued_rows": row_count,
                    },
                }
            )

        result = run_import_job(job_id, token, request.user.pk, branch_id)
        if not result.get("ok"):
            return Response(
                {
                    "success": False,
                    "error": {"message": result.get("error", "Import failed")},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "success": True,
                "data": {
                    "job_id": job.id,
                    "async": False,
                    "imported": result.get("imported", 0),
                    "failed": result.get("failed", []),
                },
            }
        )

    def _import_legacy(self, request, token: str, cached: dict, branch_id: int | None):
        """Run a real legacy import using the cached CSV text from validate.

        Big legacy files (>50 valid rows) are queued through Celery so the
        request returns immediately; smaller jobs run synchronously.
        """
        if int(cached.get("admin_user_id")) != int(request.user.pk):
            return Response(
                {"success": False, "error": {"message": "Validation token does not belong to this user"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        job_id = int(cached.get("job_id"))
        job = BulkUploadJob.objects.filter(pk=job_id).first()
        if not job:
            return Response(
                {"success": False, "error": {"message": "Bulk upload job not found"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if branch_id is not None and job.branch_id != branch_id:
            job.branch_id = branch_id
            job.save(update_fields=["branch"])

        valid_rows = int(cached.get("valid_rows") or 0)
        if valid_rows > LEGACY_ASYNC_ROW_THRESHOLD:
            async_result = bulk_import_legacy_profiles_task.delay(
                job_id, token, request.user.pk, branch_id
            )
            job.status = BulkUploadJob.STATUS_QUEUED
            job.task_id = async_result.id
            job.save(update_fields=["status", "task_id"])
            return Response(
                {
                    "success": True,
                    "data": {
                        "job_id": job.id,
                        "async": True,
                        "legacy": True,
                        "task_id": async_result.id,
                        "queued_rows": valid_rows,
                    },
                }
            )

        from master.models import Branch as MasterBranchLocal

        branch = MasterBranchLocal.objects.filter(pk=branch_id, is_active=True).first() if branch_id else None
        job.mark_processing()
        try:
            result = import_legacy_csv_text(cached["csv_text"], branch=branch)
        except Exception as exc:  # noqa: BLE001 - capture and report
            job.mark_failed(str(exc))
            return Response(
                {"success": False, "error": {"message": str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Combine row-level skip errors from validate with import-time failures.
        existing_errors = list(cached.get("errors") or [])
        all_failures = existing_errors + list(result.get("failed") or [])
        job.mark_completed(result.get("imported", 0), all_failures)
        from .legacy_runner import delete_cached_legacy_payload as _delete_legacy

        _delete_legacy(token)
        return Response(
            {
                "success": True,
                "data": {
                    "job_id": job.id,
                    "async": False,
                    "legacy": True,
                    "imported": result.get("imported", 0),
                    "failed": all_failures,
                },
            }
        )


class BulkUploadTaskStatusView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminOrBranchManager]

    def get(self, request, task_id):
        job = BulkUploadJob.objects.filter(task_id=task_id).first()
        if job:
            role = getattr(request.user, "role", None)
            if role == AdminUser.ROLE_BRANCH_MANAGER and job.branch_id != getattr(request.user, "branch_id", None):
                return Response({"success": False, "error": {"message": "Access denied"}}, status=403)
        r = AsyncResult(task_id, app=celery_app)
        payload: dict = {
            "state": r.state,
        }
        if job:
            payload["job"] = {
                "job_id": job.id,
                "status": job.status,
                "imported_count": job.imported_count,
                "error_rows": job.error_rows,
            }
        if r.successful():
            payload["result"] = r.result
        elif r.failed():
            payload["error"] = str(r.result) if r.result else "Task failed"
        return Response({"success": True, "data": payload})


class BulkUploadHistoryView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminOrBranchManager]

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            from rest_framework.settings import api_settings

            pc = api_settings.DEFAULT_PAGINATION_CLASS
            self._paginator = pc() if pc else None
        return self._paginator

    def get(self, request):
        qs = BulkUploadJob.objects.select_related("uploaded_by", "branch")
        role = getattr(request.user, "role", None)
        if role == AdminUser.ROLE_BRANCH_MANAGER:
            qs = qs.filter(branch_id=getattr(request.user, "branch_id", None))

        status_filter = (request.query_params.get("status") or "").strip().lower()
        if status_filter:
            qs = qs.filter(status=status_filter)

        qs = qs.order_by("-created_at")
        if self.paginator:
            page = self.paginator.paginate_queryset(qs, request, view=self)
            ser = BulkUploadJobHistorySerializer(page, many=True)
            paged = self.paginator.get_paginated_response(ser.data)
            return Response({"success": True, "data": paged.data})
        ser = BulkUploadJobHistorySerializer(qs[:100], many=True)
        return Response({"success": True, "data": {"count": len(ser.data), "results": ser.data}})
