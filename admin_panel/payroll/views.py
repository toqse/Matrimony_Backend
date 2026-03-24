from datetime import date, datetime, time
from decimal import Decimal
from io import BytesIO

from django.db import transaction as db_transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.commissions.models import Commission
from admin_panel.permissions import IsBranchManager
from admin_panel.staff_mgmt.models import StaffProfile
from master.models import Branch as MasterBranch

from .models import SalaryRecord
from .serializers import (
    BranchSalaryRecordDetailSerializer,
    BranchSalaryRecordListSerializer,
    SalaryRecordListSerializer,
    SalaryRecordSerializer,
    _role_can_approve,
    _role_can_generate,
    _role_can_mark_paid,
)


def _escape_pdf_text(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(lines: list[str]) -> bytes:
    text_lines = ["BT", "/F1 12 Tf", "50 780 Td"]
    for i, line in enumerate(lines):
        if i:
            text_lines.append("0 -18 Td")
        text_lines.append(f"({_escape_pdf_text(line)}) Tj")
    text_lines.append("ET")
    stream = "\n".join(text_lines).encode("latin-1", errors="replace")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        b"4 0 obj\n<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    pdf = BytesIO()
    pdf.write(b"%PDF-1.4\n")
    offs = [0]
    for obj in objects:
        offs.append(pdf.tell())
        pdf.write(obj)
    xref = pdf.tell()
    pdf.write(f"xref\n0 {len(offs)}\n".encode())
    pdf.write(b"0000000000 65535 f \n")
    for o in offs[1:]:
        pdf.write(f"{o:010d} 00000 n \n".encode())
    pdf.write(f"trailer\n<< /Size {len(offs)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return pdf.getvalue()


def _staff_profile_for_admin_user(user):
    # Prefer direct relation (stable), keep mobile fallback for legacy rows.
    staff = StaffProfile.objects.filter(admin_user=user, is_deleted=False).first()
    if staff:
        return staff
    mobile = (getattr(user, "mobile", "") or "").strip()
    mobile10 = mobile[-10:] if mobile.startswith("+91") else mobile
    return StaffProfile.objects.filter(mobile=mobile10, is_deleted=False).first()


def _manager_branch_code(user):
    return (
        MasterBranch.objects.filter(pk=getattr(user, "branch_id", None))
        .values_list("code", flat=True)
        .first()
    )


def parse_month_string(s: str):
    s = (s or "").strip()
    if len(s) != 7 or s[4] != "-":
        return None, "Invalid month format, use YYYY-MM"
    try:
        y = int(s[:4])
        m = int(s[5:7])
        if m < 1 or m > 12:
            return None, "Invalid month format, use YYYY-MM"
        return date(y, m, 1), None
    except ValueError:
        return None, "Invalid month format, use YYYY-MM"


def parse_month_string_mm_yyyy(s: str):
    """Branch payroll month param: MM-YYYY (e.g. 02-2026)."""
    s = (s or "").strip()
    if len(s) != 7 or s[2] != "-":
        return None, "Invalid month format. Use MM-YYYY."
    try:
        m = int(s[:2])
        y = int(s[3:7])
        if m < 1 or m > 12:
            return None, "Invalid month format. Use MM-YYYY."
        return date(y, m, 1), None
    except ValueError:
        return None, "Invalid month format. Use MM-YYYY."


def month_paid_at_bounds(month_start: date):
    start = timezone.make_aware(datetime.combine(month_start, time.min))
    if month_start.month == 12:
        next_first = date(month_start.year + 1, 1, 1)
    else:
        next_first = date(month_start.year, month_start.month + 1, 1)
    end_exclusive = timezone.make_aware(datetime.combine(next_first, time.min))
    return start, end_exclusive


def month_date_bounds(month_start: date):
    if month_start.month == 12:
        next_first = date(month_start.year + 1, 1, 1)
    else:
        next_first = date(month_start.year, month_start.month + 1, 1)
    month_end = next_first - timezone.timedelta(days=1)
    return month_start, month_end


def is_future_month(month_start: date) -> bool:
    today = timezone.localdate()
    cur_first = date(today.year, today.month, 1)
    return month_start > cur_first


def commission_sum_paid_in_month(staff_id: int, month_start: date) -> Decimal:
    start, end_ex = month_paid_at_bounds(month_start)
    total = Commission.objects.filter(
        staff_id=staff_id,
        status=Commission.STATUS_PAID,
        paid_at__gte=start,
        paid_at__lt=end_ex,
    ).aggregate(t=Sum("commission_amt"))["t"]
    return Decimal(total or 0)


def _default_month_string() -> str:
    t = timezone.localdate()
    return f"{t.year:04d}-{t.month:02d}"


def _default_month_string_mm_yyyy() -> str:
    t = timezone.localdate()
    return f"{t.month:02d}-{t.year:04d}"


def _scoped_salary_queryset(request, force_staff_id=None):
    qs = SalaryRecord.objects.select_related("staff", "branch", "approved_by")
    role = getattr(request.user, "role", None)
    if force_staff_id is not None:
        return qs.filter(staff_id=force_staff_id)
    if role == AdminUser.ROLE_STAFF:
        staff = _staff_profile_for_admin_user(request.user)
        return qs.filter(staff=staff) if staff else qs.none()
    if role == AdminUser.ROLE_BRANCH_MANAGER:
        code = _manager_branch_code(request.user)
        return qs.filter(branch__code=code) if code else qs.none()
    return qs


def _apply_list_filters(request, qs, *, latest_month_when_missing: bool = False):
    month_s = (request.query_params.get("month") or "").strip()
    if month_s:
        md, err = parse_month_string(month_s)
        if err:
            return None, Response({"success": False, "error": {"code": 400, "message": err}}, status=400)
    else:
        if latest_month_when_missing:
            # For self payroll view, prefer a finalized month by default so UI doesn't
            # show a newer draft month while an older paid/approved month exists.
            latest_month = (
                qs.exclude(status=SalaryRecord.STATUS_DRAFT).order_by("-month").values_list("month", flat=True).first()
            )
            if not latest_month:
                latest_month = qs.order_by("-month").values_list("month", flat=True).first()
            md = latest_month or timezone.localdate().replace(day=1)
        else:
            md = parse_month_string(_default_month_string())[0]
    qs = qs.filter(month=md)

    status_filter = (request.query_params.get("status") or "").strip().lower()
    if status_filter:
        if status_filter not in {SalaryRecord.STATUS_DRAFT, SalaryRecord.STATUS_APPROVED, SalaryRecord.STATUS_PAID}:
            return None, Response(
                {"success": False, "error": {"code": 400, "message": "Invalid status filter"}},
                status=400,
            )
        qs = qs.filter(status=status_filter)

    branch_id = request.query_params.get("branch_id")
    if branch_id:
        role = getattr(request.user, "role", None)
        if role == AdminUser.ROLE_BRANCH_MANAGER:
            own_code = _manager_branch_code(request.user)
            from admin_panel.branches.models import Branch

            req_code = Branch.objects.filter(pk=branch_id).values_list("code", flat=True).first()
            if req_code != own_code:
                return None, Response(
                    {"success": False, "error": {"code": 403, "message": "Access denied"}},
                    status=403,
                )
        qs = qs.filter(branch_id=branch_id)

    return qs, None


class PayrollListAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            from rest_framework.settings import api_settings

            pagination_class = api_settings.DEFAULT_PAGINATION_CLASS
            self._paginator = pagination_class() if pagination_class else None
        return self._paginator

    def paginate_queryset(self, queryset, request):
        if self.paginator is None:
            return None
        return self.paginator.paginate_queryset(queryset, request, view=self)

    def get_paginated_response(self, data):
        return self.paginator.get_paginated_response(data)

    def get(self, request):
        qs = _scoped_salary_queryset(request)
        qs, err = _apply_list_filters(request, qs)
        if err:
            return err
        qs = qs.order_by("staff__name")
        page = self.paginate_queryset(qs, request)
        ser = SalaryRecordListSerializer(page if page is not None else qs, many=True)
        if page is not None:
            paged = self.get_paginated_response(ser.data)
            return Response({"success": True, "data": paged.data})
        return Response({"success": True, "data": {"count": len(ser.data), "results": ser.data}})


class PayrollSummaryAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = _scoped_salary_queryset(request)
        month_s = (request.query_params.get("month") or "").strip() or _default_month_string()
        md, err = parse_month_string(month_s)
        if err:
            return Response({"success": False, "error": {"code": 400, "message": err}}, status=400)
        qs = qs.filter(month=md)

        branch_id = request.query_params.get("branch_id")
        if branch_id:
            role = getattr(request.user, "role", None)
            if role == AdminUser.ROLE_BRANCH_MANAGER:
                own_code = _manager_branch_code(request.user)
                from admin_panel.branches.models import Branch

                req_code = Branch.objects.filter(pk=branch_id).values_list("code", flat=True).first()
                if req_code != own_code:
                    return Response(
                        {"success": False, "error": {"code": 403, "message": "Access denied"}},
                        status=403,
                    )
            qs = qs.filter(branch_id=branch_id)

        agg = qs.aggregate(
            total_net=Sum("net"),
            total_gross=Sum("gross"),
            staff_count=Count("id", distinct=True),
            pending_drafts=Count("id", filter=Q(status=SalaryRecord.STATUS_DRAFT)),
        )
        data = {
            "total_net_payroll": float(agg["total_net"] or 0),
            "total_gross": float(agg["total_gross"] or 0),
            "staff_count": agg["staff_count"] or 0,
            "pending_drafts": agg["pending_drafts"] or 0,
            "month": month_s,
        }
        return Response({"success": True, "data": data})


class GeneratePayrollAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _role_can_generate(request.user):
            return Response(
                {"success": False, "error": {"code": 403, "message": "Insufficient permissions"}},
                status=403,
            )
        month_s = (request.data.get("month") or "").strip()
        md, err = parse_month_string(month_s)
        if err:
            return Response({"success": False, "error": {"code": 400, "message": err}}, status=400)
        if is_future_month(md):
            return Response(
                {"success": False, "error": {"code": 400, "message": "Cannot generate salary for future months"}},
                status=400,
            )
        _, month_end = month_date_bounds(md)
        staff_qs = (
            StaffProfile.objects.filter(is_active=True, is_deleted=False)
            .filter(Q(joining_date__isnull=True) | Q(joining_date__lte=month_end))
            .select_related("branch")
        )
        created = 0
        with db_transaction.atomic():
            if SalaryRecord.objects.filter(month=md).exists():
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": 400,
                            "message": "Salary already generated for this month. Use individual edits.",
                        },
                    },
                    status=400,
                )
            for sp in staff_qs:
                comm = commission_sum_paid_in_month(sp.id, md)
                basic = Decimal(sp.basic_salary or 0)
                allowances = Decimal("0")
                deductions = Decimal("0")
                gross = basic + comm + allowances
                net = gross - deductions
                SalaryRecord.objects.create(
                    staff=sp,
                    branch=sp.branch,
                    month=md,
                    basic=basic,
                    commission=comm,
                    allowances=allowances,
                    deductions=deductions,
                    gross=gross,
                    net=net,
                    status=SalaryRecord.STATUS_DRAFT,
                )
                created += 1

        return Response(
            {
                "success": True,
                "data": {"month": month_s, "records_created": created},
            },
            status=status.HTTP_201_CREATED,
        )


class PayrollDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        qs = _scoped_salary_queryset(request)
        obj = qs.filter(pk=pk).first()
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Salary record not found"}},
                status=404,
            )
        return Response({"success": True, "data": SalaryRecordSerializer(obj).data})


class ApprovePayrollAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not _role_can_approve(request.user):
            return Response(
                {"success": False, "error": {"code": 403, "message": "Insufficient permissions"}},
                status=403,
            )
        qs = SalaryRecord.objects.select_related("staff", "branch").filter(pk=pk)
        obj = qs.first()
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Salary record not found"}},
                status=404,
            )
        role = getattr(request.user, "role", None)
        if role == AdminUser.ROLE_BRANCH_MANAGER:
            code = _manager_branch_code(request.user)
            if not code or obj.branch.code != code:
                return Response(
                    {"success": False, "error": {"code": 403, "message": "Access denied"}},
                    status=403,
                )
        if obj.status != SalaryRecord.STATUS_DRAFT:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Only draft records can be approved"}},
                status=400,
            )
        obj.status = SalaryRecord.STATUS_APPROVED
        obj.approved_by = request.user
        obj.save(update_fields=["status", "approved_by", "updated_at"])
        return Response({"success": True, "data": SalaryRecordSerializer(obj).data})


class MarkPaidPayrollAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not _role_can_mark_paid(request.user):
            return Response(
                {"success": False, "error": {"code": 403, "message": "Insufficient permissions"}},
                status=403,
            )
        obj = SalaryRecord.objects.filter(pk=pk).first()
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Salary record not found"}},
                status=404,
            )
        if obj.status != SalaryRecord.STATUS_APPROVED:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Salary must be approved before marking as paid"},
                },
                status=400,
            )
        obj.status = SalaryRecord.STATUS_PAID
        obj.paid_at = timezone.now()
        obj.save(update_fields=["status", "paid_at", "updated_at"])
        return Response({"success": True, "data": SalaryRecordSerializer(obj).data})


class PayrollDownloadAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        qs = _scoped_salary_queryset(request)
        obj = qs.select_related("staff", "branch").filter(pk=pk).first()
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Salary record not found"}},
                status=404,
            )
        month_label = obj.month.strftime("%B %Y") if obj.month else ""
        lines = [
            "Salary Slip",
            f"Staff: {obj.staff.name} ({obj.staff.emp_code})",
            f"Branch: {obj.branch.name}",
            f"Month: {month_label}",
            f"Basic: {obj.basic}",
            f"Commission: {obj.commission}",
            f"Allowances: {obj.allowances}",
            f"Deductions: {obj.deductions}",
            f"Gross: {obj.gross}",
            f"Net: {obj.net}",
            f"Status: {obj.status}",
        ]
        pdf = _build_simple_pdf(lines)
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="salary_{obj.id}_slip.pdf"'
        return resp


class StaffPayrollListAPIView(PayrollListAPIView):
    def get(self, request):
        role = getattr(request.user, "role", None)
        if role not in (AdminUser.ROLE_STAFF, AdminUser.ROLE_BRANCH_MANAGER):
            return Response(
                {"success": False, "error": {"code": 403, "message": "Insufficient permissions"}},
                status=403,
            )
        staff = _staff_profile_for_admin_user(request.user)
        if not staff:
            return Response(
                {"success": False, "error": {"code": 403, "message": "Profile not found for this user"}},
                status=403,
            )
        qs = _scoped_salary_queryset(request, force_staff_id=staff.id)
        qs, err = _apply_list_filters(request, qs, latest_month_when_missing=True)
        if err:
            return err
        qs = qs.order_by("-month")
        page = self.paginate_queryset(qs, request)
        ser = SalaryRecordListSerializer(page if page is not None else qs, many=True)
        if page is not None:
            paged = self.get_paginated_response(ser.data)
            return Response({"success": True, "data": paged.data})
        return Response({"success": True, "data": {"count": len(ser.data), "results": ser.data}})


def _branch_manager_code_or_error(request):
    code = _manager_branch_code(request.user)
    if not code:
        return None, Response(
            {
                "success": False,
                "error": {
                    "code": 400,
                    "message": "No branch assigned to your account. Contact admin.",
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return code, None


def _salary_record_for_branch_manager(request, pk, *, wrong_branch_as_404: bool):
    code, err = _branch_manager_code_or_error(request)
    if err:
        return None, err
    obj = (
        SalaryRecord.objects.select_related("staff", "branch", "approved_by")
        .filter(pk=pk)
        .first()
    )
    if not obj:
        return None, Response(
            {"success": False, "error": {"code": 404, "message": "Salary record not found"}},
            status=status.HTTP_404_NOT_FOUND,
        )
    if obj.branch.code != code:
        if wrong_branch_as_404:
            return None, Response(
                {"success": False, "error": {"code": 404, "message": "Salary record not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return None, Response(
            {
                "success": False,
                "error": {
                    "code": 403,
                    "message": "You can only approve salary records for your own branch staff.",
                },
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return obj, None


def _apply_branch_list_filters(request, qs):
    month_s = (request.query_params.get("month") or "").strip()
    if month_s:
        md, err = parse_month_string_mm_yyyy(month_s)
        if err:
            return None, None, Response({"success": False, "error": {"code": 400, "message": err}}, status=400)
    else:
        # When month is omitted, use the latest available salary month for this branch.
        # This prevents empty table responses for branches that don't have current-month payroll yet.
        latest_month = qs.order_by("-month").values_list("month", flat=True).first()
        md = latest_month or timezone.localdate().replace(day=1)
    qs = qs.filter(month=md)
    resolved_month = f"{md.month:02d}-{md.year:04d}"

    status_filter = (request.query_params.get("status") or "").strip().lower()
    if status_filter:
        if status_filter not in {SalaryRecord.STATUS_DRAFT, SalaryRecord.STATUS_APPROVED, SalaryRecord.STATUS_PAID}:
            return None, None, Response(
                {"success": False, "error": {"code": 400, "message": "Invalid status filter"}},
                status=400,
            )
        qs = qs.filter(status=status_filter)

    return qs, resolved_month, None


class BranchPayrollSummaryAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def get(self, request):
        code, err = _branch_manager_code_or_error(request)
        if err:
            return err
        qs_all = SalaryRecord.objects.filter(branch__code=code)
        month_s = (request.query_params.get("month") or "").strip()
        if month_s:
            md, merr = parse_month_string_mm_yyyy(month_s)
            if merr:
                return Response({"success": False, "error": {"code": 400, "message": merr}}, status=400)
        else:
            latest_month = qs_all.order_by("-month").values_list("month", flat=True).first()
            md = latest_month or timezone.localdate().replace(day=1)
            month_s = f"{md.month:02d}-{md.year:04d}"

        qs = qs_all.filter(month=md)
        agg = qs.aggregate(
            branch_net=Sum("net"),
            staff_count=Count("id", distinct=True),
            pending_drafts=Count("id", filter=Q(status=SalaryRecord.STATUS_DRAFT)),
            paid_count=Count("id", filter=Q(status=SalaryRecord.STATUS_PAID)),
        )
        return Response(
            {
                "success": True,
                "data": {
                    "month": month_s,
                    "branch_net_payroll": float(agg["branch_net"] or 0),
                    "branch_net_pay": float(agg["branch_net"] or 0),
                    "staff_count": agg["staff_count"] or 0,
                    "pending_drafts": agg["pending_drafts"] or 0,
                    "paid_count": agg["paid_count"] or 0,
                    "paid": agg["paid_count"] or 0,
                },
            }
        )


class BranchPayrollListAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            from rest_framework.settings import api_settings

            pagination_class = api_settings.DEFAULT_PAGINATION_CLASS
            self._paginator = pagination_class() if pagination_class else None
        return self._paginator

    def paginate_queryset(self, queryset, request):
        if self.paginator is None:
            return None
        return self.paginator.paginate_queryset(queryset, request, view=self)

    def get_paginated_response(self, data):
        return self.paginator.get_paginated_response(data)

    def get(self, request):
        code, err = _branch_manager_code_or_error(request)
        if err:
            return err
        qs = _scoped_salary_queryset(request)
        qs, resolved_month, ferr = _apply_branch_list_filters(request, qs)
        if ferr:
            return ferr
        qs = qs.order_by("staff__name")
        page = self.paginate_queryset(qs, request)
        ser = BranchSalaryRecordListSerializer(
            page if page is not None else qs,
            many=True,
            context={"request": request},
        )
        if page is not None:
            paged = self.get_paginated_response(ser.data)
            paged.data["month"] = resolved_month
            return Response({"success": True, "data": paged.data})
        return Response(
            {
                "success": True,
                "data": {
                    "count": len(ser.data),
                    "results": ser.data,
                    "month": resolved_month,
                },
            }
        )


class BranchPayrollDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def get(self, request, pk):
        obj, err = _salary_record_for_branch_manager(request, pk, wrong_branch_as_404=True)
        if err:
            return err
        return Response(
            {
                "success": True,
                "data": BranchSalaryRecordDetailSerializer(obj, context={"request": request}).data,
            }
        )


class BranchApprovePayrollAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def patch(self, request, pk):
        obj, err = _salary_record_for_branch_manager(request, pk, wrong_branch_as_404=False)
        if err:
            return err
        if obj.status != SalaryRecord.STATUS_DRAFT:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Only draft records can be approved."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj.status = SalaryRecord.STATUS_APPROVED
        obj.approved_by = request.user
        obj.save(update_fields=["status", "approved_by", "updated_at"])
        obj = SalaryRecord.objects.select_related("staff", "branch", "approved_by").filter(pk=obj.pk).first()
        return Response(
            {
                "success": True,
                "data": BranchSalaryRecordDetailSerializer(obj, context={"request": request}).data,
            }
        )


class BranchGeneratePayrollForbiddenAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def post(self, request):
        return Response(
            {
                "success": False,
                "error": {"code": 403, "message": "Salary generation is an admin-only action."},
            },
            status=status.HTTP_403_FORBIDDEN,
        )


class BranchMarkPaidPayrollForbiddenAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def patch(self, request, pk):
        return Response(
            {
                "success": False,
                "error": {"code": 403, "message": "Marking salary as paid is an admin-only action."},
            },
            status=status.HTTP_403_FORBIDDEN,
        )


class BranchPayrollDownloadAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def get(self, request, pk):
        obj, err = _salary_record_for_branch_manager(request, pk, wrong_branch_as_404=True)
        if err:
            return err
        month_label = obj.month.strftime("%B %Y") if obj.month else ""
        lines = [
            "Salary Slip",
            f"Staff: {obj.staff.name} ({obj.staff.emp_code})",
            f"Branch: {obj.branch.name}",
            f"Month: {month_label}",
            f"Basic: {obj.basic}",
            f"Commission: {obj.commission}",
            f"Allowances: {obj.allowances}",
            f"Deductions: {obj.deductions}",
            f"Gross: {obj.gross}",
            f"Net: {obj.net}",
            f"Status: {obj.status}",
        ]
        pdf = _build_simple_pdf(lines)
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="salary_{obj.id}_slip.pdf"'
        return resp
