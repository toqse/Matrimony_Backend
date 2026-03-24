from decimal import Decimal
from io import BytesIO

from django.db.models import Case, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.audit_log.mixins import AuditLogMixin
from admin_panel.audit_log.models import AuditLog
from admin_panel.permissions import IsBranchManager
from admin_panel.staff_mgmt.models import StaffProfile
from master.models import Branch as MasterBranch

from .models import Commission
from .serializers import CommissionCreateSerializer, CommissionSerializer


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


class _BaseCommissionListAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]
    force_staff_scope = False

    def _scoped_queryset(self, request):
        qs = Commission.objects.select_related(
            "staff", "branch", "customer", "subscription", "subscription__plan", "plan"
        )
        role = getattr(request.user, "role", None)
        if self.force_staff_scope or role == AdminUser.ROLE_STAFF:
            staff = _staff_profile_for_admin_user(request.user)
            qs = qs.filter(staff=staff) if staff else qs.none()
        elif role == AdminUser.ROLE_BRANCH_MANAGER:
            code = _manager_branch_code(request.user)
            qs = qs.filter(branch__code=code) if code else qs.none()
        return qs

    def _apply_filters(self, request, qs):
        status_filter = (request.query_params.get("status") or "").strip().lower()
        if status_filter and status_filter not in {
            Commission.STATUS_PENDING,
            Commission.STATUS_APPROVED,
            Commission.STATUS_PAID,
            Commission.STATUS_CANCELLED,
        }:
            return None, Response(
                {"success": False, "error": {"code": 400, "message": "Invalid status filter"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if status_filter:
            qs = qs.filter(status=status_filter)

        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(customer__name__icontains=search)
                | Q(customer__matri_id__icontains=search)
                | Q(staff__name__icontains=search)
            )

        branch_id = request.query_params.get("branch_id")
        if branch_id:
            role = getattr(request.user, "role", None)
            if role == AdminUser.ROLE_BRANCH_MANAGER:
                own_code = _manager_branch_code(request.user)
                req_code = (
                    MasterBranch.objects.filter(pk=branch_id).values_list("code", flat=True).first()
                )
                if req_code != own_code:
                    return None, Response(
                        {"success": False, "error": {"code": 403, "message": "Access denied"}},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            qs = qs.filter(branch_id=branch_id)

        staff_id = request.query_params.get("staff_id")
        if staff_id:
            qs = qs.filter(staff_id=staff_id)
        return qs, None

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            from rest_framework.settings import api_settings
            pagination_class = api_settings.DEFAULT_PAGINATION_CLASS
            self._paginator = pagination_class() if pagination_class else None
        return self._paginator

    def paginate_queryset(self, queryset):
        if self.paginator is None:
            return None
        return self.paginator.paginate_queryset(queryset, self.request, view=self)

    def get_paginated_response(self, data):
        return self.paginator.get_paginated_response(data)

    def get(self, request):
        qs = self._scoped_queryset(request)
        qs, err = self._apply_filters(request, qs)
        if err:
            return err
        summary_qs = qs
        page = self.paginate_queryset(qs.order_by("-created_at"))
        ser = CommissionSerializer(page if page is not None else qs, many=True)
        _dec = DecimalField(max_digits=12, decimal_places=2)
        _z = Value(Decimal("0"), output_field=_dec)
        summary_row = summary_qs.aggregate(
            total_pending=Coalesce(
                Sum(
                    Case(
                        When(status=Commission.STATUS_PENDING, then=F("commission_amt")),
                        default=_z,
                        output_field=_dec,
                    )
                ),
                _z,
            ),
            approved=Coalesce(
                Sum(
                    Case(
                        When(status=Commission.STATUS_APPROVED, then=F("commission_amt")),
                        default=_z,
                        output_field=_dec,
                    )
                ),
                _z,
            ),
            paid=Coalesce(
                Sum(
                    Case(
                        When(status=Commission.STATUS_PAID, then=F("commission_amt")),
                        default=_z,
                        output_field=_dec,
                    )
                ),
                _z,
            ),
            grand_total=Coalesce(Sum("commission_amt"), _z),
        )
        summary = {
            "total_pending": float(summary_row["total_pending"] or 0),
            "approved": float(summary_row["approved"] or 0),
            "paid": float(summary_row["paid"] or 0),
            "grand_total": float(summary_row["grand_total"] or 0),
        }
        if page is not None:
            data = self.get_paginated_response(ser.data).data
            data["summary"] = summary
            return Response({"success": True, "data": data})
        return Response({"success": True, "data": {"summary": summary, "count": len(ser.data), "results": ser.data}})


class AdminCommissionsListAPIView(AuditLogMixin, _BaseCommissionListAPIView):
    def post(self, request):
        role = getattr(request.user, "role", None)
        if role == AdminUser.ROLE_STAFF:
            return Response(
                {"success": False, "error": {"code": 403, "message": "Insufficient permissions"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        ser = CommissionCreateSerializer(data=request.data, context={"request": request})
        if not ser.is_valid():
            return Response(
                {"success": False, "error": {"code": 400, "message": "Validation failed", "details": ser.errors}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj = ser.save()
        obj = (
            Commission.objects.select_related(
                "staff", "branch", "customer", "subscription", "subscription__plan", "plan"
            )
            .filter(pk=obj.pk)
            .first()
        )
        self.log_action(
            action=AuditLog.ACTION_COMMISSION_CREATE,
            resource=f"commission:{obj.id}",
            details=f"Commission created for {obj.customer.matri_id}.",
            new_value={
                "status": obj.status,
                "commission_amt": str(obj.commission_amt),
            },
        )
        return Response({"success": True, "data": CommissionSerializer(obj).data}, status=status.HTTP_201_CREATED)


class StaffCommissionsListAPIView(_BaseCommissionListAPIView):
    force_staff_scope = True


class CommissionDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        qs = Commission.objects.select_related(
            "staff", "branch", "customer", "subscription", "subscription__plan", "plan"
        )
        role = getattr(request.user, "role", None)
        if role == AdminUser.ROLE_STAFF:
            staff = _staff_profile_for_admin_user(request.user)
            qs = qs.filter(staff=staff) if staff else qs.none()
        elif role == AdminUser.ROLE_BRANCH_MANAGER:
            code = _manager_branch_code(request.user)
            qs = qs.filter(branch__code=code) if code else qs.none()
        obj = qs.filter(pk=pk).first()
        if not obj:
            return Response({"success": False, "error": {"code": 404, "message": "Commission not found"}}, status=404)
        return Response({"success": True, "data": CommissionSerializer(obj).data})


class _CommissionActionBase(AuditLogMixin, APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _check_admin(self, request):
        if getattr(request.user, "role", None) != AdminUser.ROLE_ADMIN:
            return Response(
                {"success": False, "error": {"code": 403, "message": "Insufficient permissions"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def _get_obj(self, pk):
        return (
            Commission.objects.select_related(
                "staff", "branch", "customer", "subscription", "subscription__plan", "plan", "approved_by"
            )
            .filter(pk=pk)
            .first()
        )


class ApproveCommissionAPIView(_CommissionActionBase):
    def patch(self, request, pk):
        deny = self._check_admin(request)
        if deny:
            return deny
        obj = self._get_obj(pk)
        if not obj:
            return Response({"success": False, "error": {"code": 404, "message": "Commission not found"}}, status=404)
        if obj.status != Commission.STATUS_PENDING:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Only pending commissions can be approved"}},
                status=400,
            )
        obj.status = Commission.STATUS_APPROVED
        obj.approved_by = request.user
        obj.save(update_fields=["status", "approved_by", "updated_at"])
        self.log_action(
            action=AuditLog.ACTION_COMMISSION_UPDATE,
            resource=f"commission:{obj.id}",
            details="Commission approved.",
            old_value={"status": Commission.STATUS_PENDING},
            new_value={"status": obj.status},
        )
        return Response({"success": True, "data": CommissionSerializer(obj).data})


class MarkPaidCommissionAPIView(_CommissionActionBase):
    def patch(self, request, pk):
        deny = self._check_admin(request)
        if deny:
            return deny
        obj = self._get_obj(pk)
        if not obj:
            return Response({"success": False, "error": {"code": 404, "message": "Commission not found"}}, status=404)
        if obj.status != Commission.STATUS_APPROVED:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Commission must be approved before marking paid"},
                },
                status=400,
            )
        obj.status = Commission.STATUS_PAID
        obj.paid_at = timezone.now()
        obj.save(update_fields=["status", "paid_at", "updated_at"])
        self.log_action(
            action=AuditLog.ACTION_COMMISSION_UPDATE,
            resource=f"commission:{obj.id}",
            details="Commission marked as paid.",
            old_value={"status": Commission.STATUS_APPROVED},
            new_value={"status": obj.status},
        )
        return Response({"success": True, "data": CommissionSerializer(obj).data})


class CancelCommissionAPIView(_CommissionActionBase):
    def patch(self, request, pk):
        deny = self._check_admin(request)
        if deny:
            return deny
        obj = self._get_obj(pk)
        if not obj:
            return Response({"success": False, "error": {"code": 404, "message": "Commission not found"}}, status=404)
        if obj.status != Commission.STATUS_PENDING:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Only pending commissions can be cancelled"}},
                status=400,
            )
        obj.status = Commission.STATUS_CANCELLED
        obj.save(update_fields=["status", "updated_at"])
        self.log_action(
            action=AuditLog.ACTION_COMMISSION_UPDATE,
            resource=f"commission:{obj.id}",
            details="Commission cancelled.",
            old_value={"status": Commission.STATUS_PENDING},
            new_value={"status": obj.status},
        )
        return Response({"success": True, "data": CommissionSerializer(obj).data})


class BulkApproveCommissionAPIView(_CommissionActionBase):
    def post(self, request):
        deny = self._check_admin(request)
        if deny:
            return deny
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Please select at least one commission"}},
                status=400,
            )
        qs = Commission.objects.filter(id__in=ids, status=Commission.STATUS_PENDING)
        count = qs.count()
        qs.update(status=Commission.STATUS_APPROVED, approved_by=request.user, updated_at=timezone.now())
        return Response({"success": True, "data": {"approved_count": count}})


class CommissionSlipAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        obj = (
            Commission.objects.select_related(
                "staff", "branch", "customer", "subscription", "subscription__plan", "plan"
            )
            .filter(pk=pk)
            .first()
        )
        if not obj:
            return Response({"success": False, "error": {"code": 404, "message": "Commission not found"}}, status=404)
        role = getattr(request.user, "role", None)
        if role == AdminUser.ROLE_STAFF:
            staff = _staff_profile_for_admin_user(request.user)
            if not staff or staff.id != obj.staff_id:
                return Response({"success": False, "error": {"code": 403, "message": "Insufficient permissions"}}, status=403)
        plan_name = ""
        if obj.subscription_id and getattr(obj.subscription, "plan", None):
            plan_name = obj.subscription.plan.name or ""
        elif obj.plan_id and obj.plan:
            plan_name = obj.plan.name or ""
        lines = [
            "Commission Slip",
            f"Date: {obj.created_at.date()}",
            f"Staff: {obj.staff.name} ({obj.staff.emp_code})",
            f"Branch: {obj.branch.name}",
            f"Customer: {obj.customer.name} ({obj.customer.matri_id})",
            f"Plan: {plan_name or '-'}",
            f"Sale Amount: {obj.sale_amount}",
            f"Rate: {obj.commission_rate}%",
            f"Commission: {obj.commission_amt}",
            f"Status: {obj.status}",
        ]
        pdf = _build_simple_pdf(lines)
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="commission_{obj.id}_slip.pdf"'
        return resp


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


def _commission_for_branch_manager(request, pk, *, wrong_branch_as_404: bool):
    """
    Returns (commission, None) or (None, Response).
    wrong_branch_as_404: True for slip (not found semantics); False for detail/actions (403).
    """
    code, err = _branch_manager_code_or_error(request)
    if err:
        return None, err
    obj = (
        Commission.objects.select_related(
            "staff", "branch", "customer", "subscription", "subscription__plan", "plan", "approved_by"
        )
        .filter(pk=pk)
        .first()
    )
    if not obj:
        return None, Response(
            {"success": False, "error": {"code": 404, "message": "Commission not found"}},
            status=status.HTTP_404_NOT_FOUND,
        )
    if obj.branch.code != code:
        if wrong_branch_as_404:
            return None, Response(
                {"success": False, "error": {"code": 404, "message": "Commission not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return None, Response(
            {
                "success": False,
                "error": {
                    "code": 403,
                    "message": "You can only manage commissions for your own branch staff.",
                },
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return obj, None


class BranchCommissionSummaryAPIView(APIView):
    """KPI cards for Branch Manager — own branch only."""

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def get(self, request):
        code, err = _branch_manager_code_or_error(request)
        if err:
            return err
        qs = Commission.objects.filter(branch__code=code)
        _dec = DecimalField(max_digits=12, decimal_places=2)
        _z = Value(Decimal("0"), output_field=_dec)
        summary_row = qs.aggregate(
            total_pending=Coalesce(
                Sum(
                    Case(
                        When(status=Commission.STATUS_PENDING, then=F("commission_amt")),
                        default=_z,
                        output_field=_dec,
                    )
                ),
                _z,
            ),
            approved=Coalesce(
                Sum(
                    Case(
                        When(status=Commission.STATUS_APPROVED, then=F("commission_amt")),
                        default=_z,
                        output_field=_dec,
                    )
                ),
                _z,
            ),
            paid=Coalesce(
                Sum(
                    Case(
                        When(status=Commission.STATUS_PAID, then=F("commission_amt")),
                        default=_z,
                        output_field=_dec,
                    )
                ),
                _z,
            ),
            total=Coalesce(Sum("commission_amt"), _z),
        )
        return Response(
            {
                "success": True,
                "data": {
                    "total_pending": float(summary_row["total_pending"] or 0),
                    "approved": float(summary_row["approved"] or 0),
                    "paid": float(summary_row["paid"] or 0),
                    "total": float(summary_row["total"] or 0),
                    "pending_amount": float(summary_row["total_pending"] or 0),
                    "approved_amount": float(summary_row["approved"] or 0),
                    "paid_amount": float(summary_row["paid"] or 0),
                    "total_amount": float(summary_row["total"] or 0),
                },
            }
        )


class BranchCommissionsListAPIView(_BaseCommissionListAPIView):
    """Paginated list for Branch Manager — no embedded summary (use summary/ endpoint)."""

    permission_classes = [IsBranchManager]

    def _scoped_queryset(self, request):
        qs = Commission.objects.select_related(
            "staff", "branch", "customer", "subscription", "subscription__plan", "plan"
        )
        code = _manager_branch_code(request.user)
        return qs.filter(branch__code=code) if code else qs.none()

    def get(self, request):
        code, err = _branch_manager_code_or_error(request)
        if err:
            return err
        qs = self._scoped_queryset(request)
        qs, ferr = self._apply_filters(request, qs)
        if ferr:
            return ferr
        page = self.paginate_queryset(qs.order_by("-created_at"))
        ser = CommissionSerializer(page if page is not None else qs, many=True)
        if page is not None:
            paginated = self.get_paginated_response(ser.data)
            return Response({"success": True, "data": paginated.data})
        return Response(
            {
                "success": True,
                "data": {"count": len(ser.data), "results": ser.data},
            }
        )


class BranchCommissionDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def get(self, request, pk):
        obj, err = _commission_for_branch_manager(request, pk, wrong_branch_as_404=False)
        if err:
            return err
        return Response({"success": True, "data": CommissionSerializer(obj).data})


class BranchApproveCommissionAPIView(AuditLogMixin, APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def patch(self, request, pk):
        obj, err = _commission_for_branch_manager(request, pk, wrong_branch_as_404=False)
        if err:
            return err
        if obj.status != Commission.STATUS_PENDING:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Only pending commissions can be approved."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj.status = Commission.STATUS_APPROVED
        obj.approved_by = request.user
        obj.save(update_fields=["status", "approved_by", "updated_at"])
        obj = (
            Commission.objects.select_related(
                "staff", "branch", "customer", "subscription", "subscription__plan", "plan", "approved_by"
            )
            .filter(pk=obj.pk)
            .first()
        )
        self.log_action(
            action=AuditLog.ACTION_COMMISSION_UPDATE,
            resource=f"commission:{obj.id}",
            details="Commission approved (branch manager).",
            old_value={"status": Commission.STATUS_PENDING},
            new_value={"status": obj.status},
        )
        return Response({"success": True, "data": CommissionSerializer(obj).data})


class BranchCancelCommissionAPIView(AuditLogMixin, APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def patch(self, request, pk):
        obj, err = _commission_for_branch_manager(request, pk, wrong_branch_as_404=False)
        if err:
            return err
        if obj.status != Commission.STATUS_PENDING:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Only pending commissions can be cancelled."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj.status = Commission.STATUS_CANCELLED
        obj.save(update_fields=["status", "updated_at"])
        obj = (
            Commission.objects.select_related(
                "staff", "branch", "customer", "subscription", "subscription__plan", "plan", "approved_by"
            )
            .filter(pk=obj.pk)
            .first()
        )
        self.log_action(
            action=AuditLog.ACTION_COMMISSION_UPDATE,
            resource=f"commission:{obj.id}",
            details="Commission cancelled (branch manager).",
            old_value={"status": Commission.STATUS_PENDING},
            new_value={"status": obj.status},
        )
        return Response({"success": True, "data": CommissionSerializer(obj).data})


class BranchMarkPaidCommissionAPIView(APIView):
    """Branch Manager cannot mark paid — reserved for Admin."""

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def patch(self, request, pk):
        return Response(
            {
                "success": False,
                "error": {"code": 403, "message": "Only admin can mark commission as paid."},
            },
            status=status.HTTP_403_FORBIDDEN,
        )


class BranchBulkApproveCommissionAPIView(AuditLogMixin, APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def post(self, request):
        code, err = _branch_manager_code_or_error(request)
        if err:
            return err
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Please select at least one commission."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = Commission.objects.filter(
            id__in=ids,
            status=Commission.STATUS_PENDING,
            branch__code=code,
        )
        count = qs.count()
        qs.update(status=Commission.STATUS_APPROVED, approved_by=request.user, updated_at=timezone.now())
        if count:
            self.log_action(
                action=AuditLog.ACTION_COMMISSION_UPDATE,
                resource="commission:bulk",
                details=f"Bulk approved {count} commission(s) (branch manager).",
                new_value={"approved_count": count},
            )
        return Response({"success": True, "data": {"approved_count": count}})


class BranchCommissionSlipAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsBranchManager]

    def get(self, request, pk):
        obj, err = _commission_for_branch_manager(request, pk, wrong_branch_as_404=True)
        if err:
            return err
        plan_name = ""
        if obj.subscription_id and getattr(obj.subscription, "plan", None):
            plan_name = obj.subscription.plan.name or ""
        elif obj.plan_id and obj.plan:
            plan_name = obj.plan.name or ""
        lines = [
            "Commission Slip",
            f"Date: {obj.created_at.date()}",
            f"Staff: {obj.staff.name} ({obj.staff.emp_code})",
            f"Branch: {obj.branch.name}",
            f"Customer: {obj.customer.name} ({obj.customer.matri_id})",
            f"Plan: {plan_name or '-'}",
            f"Sale Amount: {obj.sale_amount}",
            f"Rate: {obj.commission_rate}%",
            f"Commission: {obj.commission_amt}",
            f"Status: {obj.status}",
        ]
        pdf = _build_simple_pdf(lines)
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="commission_{obj.id}_slip.pdf"'
        return resp
