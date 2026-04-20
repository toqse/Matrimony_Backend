from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_admin_role
from admin_panel.audit_log.models import AuditLog
from admin_panel.audit_log.utils import create_audit_log
from admin_panel.staff_dashboard.services import staff_profile_for_dashboard
from admin_panel.staff_mgmt.models import StaffProfile
from admin_panel.staff_payments.models import PaymentEntry
from admin_panel.staff_payments.pagination import StaffPaymentPagination
from admin_panel.staff_payments.services import generate_receipt_no, validate_otp
from admin_panel.staff_payments.serializers import StaffPaymentCreateSerializer
from admin_panel.staff_subscriptions.services import record_staff_plan_purchase
from admin_panel.subscriptions.models import CustomerStaffAssignment
from plans.models import Plan, Transaction

# --- Exact validation / error messages (product spec) ---
MSG_MODE_REQUIRED = "mode is required."
MSG_MODE_INVALID = "Invalid payment mode. Must be: cash or gpay_upi."
MSG_CUSTOMER_MATRI_REQUIRED = "customer_matri_id is required."
MSG_CUSTOMER_NOT_FOUND = "Customer not found."
MSG_PLAN_ID_REQUIRED = "plan_id is required."
MSG_PLAN_INVALID = "Invalid or inactive plan."
MSG_AMOUNT_REQUIRED = "amount is required."
MSG_AMOUNT_NOT_POSITIVE = "Amount must be greater than zero."
def _msg_amount_mismatch(plan_price: Decimal) -> str:
    return f"Amount must equal plan price (₹{plan_price})."


MSG_REF_REQUIRED_GPay = "reference_no is required for GPay/UPI payments."
MSG_STATUS_FILTER_INVALID = "Invalid status filter. Must be: pending, verified, completed."
MSG_MODE_FILTER_INVALID = "Invalid mode filter. Must be: cash, gpay_upi."
MSG_NOT_FOUND = "Payment record not found."
MSG_VERIFY_ROLE_REQUIRED = "Access denied. Branch manager token required."
MSG_ONLY_PENDING_VERIFY = "Only pending payments can be verified."
MSG_ONLY_VERIFIED_COMPLETE = "Only verified payments can be completed."

VALID_MODES = frozenset({PaymentEntry.MODE_CASH, PaymentEntry.MODE_GPAY_UPI})
VALID_STATUSES = frozenset(
    {
        PaymentEntry.STATUS_PENDING,
        PaymentEntry.STATUS_VERIFIED,
        PaymentEntry.STATUS_COMPLETED,
    }
)


def _err_response(message: str, code: int = 400, extra: dict | None = None):
    body = {"success": False, "error": {"code": code, "message": message}}
    if extra:
        body["error"]["details"] = extra
    return Response(body, status=code)


def _err_response_code(code: str, message: str, status_code: int = 400):
    return Response(
        {
            "success": False,
            "error": {
                "code": code,
                "status": status_code,
                "message": message,
            },
        },
        status=status_code,
    )


def _resolve_staff(request):
    user = request.user
    role = normalize_admin_role(getattr(user, "role", ""))
    if role != AdminUser.ROLE_STAFF:
        return None, _err_response("Access denied. Staff token required.", 403)
    if not getattr(user, "is_active", True):
        return None, _err_response("Your account has been deactivated. Contact admin.", 403)
    sp = staff_profile_for_dashboard(user)
    if not sp:
        return None, _err_response("Staff profile not configured. Contact admin.", 400)
    if not sp.is_active:
        return None, _err_response("Your account has been deactivated. Contact admin.", 403)
    return user, None


def _staff_entries(staff_admin: AdminUser):
    return PaymentEntry.objects.filter(staff=staff_admin).select_related(
        "plan", "branch", "verified_by", "transaction"
    )


def _resolve_branch_manager(request):
    user = request.user
    role = normalize_admin_role(getattr(user, "role", ""))
    if role != AdminUser.ROLE_BRANCH_MANAGER:
        return None, _err_response(MSG_VERIFY_ROLE_REQUIRED, 403)
    if not getattr(user, "is_active", True):
        return None, _err_response("Your account has been deactivated. Contact admin.", 403)
    branch_id = getattr(user, "branch_id", None)
    if not branch_id:
        return None, _err_response("Branch manager profile not configured. Contact admin.", 400)
    return user, None


def _branch_entries(branch_manager: AdminUser):
    return PaymentEntry.objects.filter(branch_id=branch_manager.branch_id).select_related(
        "plan", "branch", "staff", "verified_by", "transaction"
    )


def _parse_decimal_amount(raw) -> tuple[Decimal | None, str | None]:
    if raw is None or raw == "":
        return None, MSG_AMOUNT_REQUIRED
    try:
        d = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return None, MSG_AMOUNT_REQUIRED
    if d <= 0:
        return None, MSG_AMOUNT_NOT_POSITIVE
    return d, None


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


def _mode_badge(mode: str) -> str:
    return "Cash" if mode == PaymentEntry.MODE_CASH else "GPay/UPI"


def _serialize_row(entry: PaymentEntry, request) -> dict:
    return {
        "receipt_id": entry.receipt_id,
        "created_by": entry.staff_id,
        "customer": {"matri_id": entry.customer_matri, "name": entry.customer_name},
        "plan": {"id": entry.plan_id, "name": entry.plan.name} if entry.plan_id else None,
        "amount": str(entry.amount),
        "mode": entry.mode,
        "mode_label": _mode_badge(entry.mode),
        "reference_no": entry.reference_no or "",
        "physical_receipt_no": entry.physical_receipt_no or "",
        "cashier_receipt_no": entry.cashier_receipt_no or "",
        "status": entry.status,
        "is_verified": bool(entry.is_verified),
        "notes": entry.notes or "",
        "created_at": entry.created_at.isoformat(),
        "verified_at": entry.verified_at.isoformat() if entry.verified_at else None,
        "transaction_id": entry.transaction_id,
        "detail_url": request.build_absolute_uri(f"/api/v1/staff/payments/{entry.receipt_id}/"),
        "receipt_pdf_url": request.build_absolute_uri(
            f"/api/v1/staff/payments/{entry.receipt_id}/receipt/"
        ),
    }


def _serialize_detail(entry: PaymentEntry, request) -> dict:
    d = _serialize_row(entry, request)
    d["branch"] = (
        {"id": entry.branch_id, "name": entry.branch.name, "code": entry.branch.code}
        if entry.branch_id
        else None
    )
    d["verified_by"] = (
        {"id": entry.verified_by_id, "name": getattr(entry.verified_by, "name", None)}
        if entry.verified_by_id
        else None
    )
    d["staff"] = {"id": entry.staff_id, "name": getattr(entry.staff, "name", None)} if entry.staff_id else None
    return d


class StaffPaymentSummaryView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        staff_admin, err = _resolve_staff(request)
        if err:
            return err
        today = timezone.localdate()
        qs_today = _staff_entries(staff_admin).filter(created_at__date=today)
        cash_sum = (
            qs_today.filter(mode=PaymentEntry.MODE_CASH).aggregate(
                s=Coalesce(Sum("amount"), Decimal("0"))
            )["s"]
            or Decimal("0")
        )
        upi_sum = (
            qs_today.filter(mode=PaymentEntry.MODE_GPAY_UPI).aggregate(
                s=Coalesce(Sum("amount"), Decimal("0"))
            )["s"]
            or Decimal("0")
        )
        pending = _staff_entries(staff_admin).filter(status=PaymentEntry.STATUS_PENDING).count()
        return Response(
            {
                "success": True,
                "data": {
                    "title": "Cash & Digital Payment Entry",
                    "subtitle": "Record cash and GPay/UPI payments from customers.",
                    "today_cash": float(cash_sum),
                    "today_upi_gpay": float(upi_sum),
                    "total_today": float(cash_sum + upi_sum),
                    "pending_count": pending,
                },
            }
        )


class StaffPaymentListCreateView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        staff_admin, err = _resolve_staff(request)
        if err:
            return err
        qs = _staff_entries(staff_admin)

        raw_mode = (request.query_params.get("mode") or "").strip().lower()
        if raw_mode:
            if raw_mode not in VALID_MODES:
                return _err_response(MSG_MODE_FILTER_INVALID)
            qs = qs.filter(mode=raw_mode)

        raw_status = (request.query_params.get("status") or "").strip().lower()
        if raw_status:
            if raw_status not in VALID_STATUSES:
                return _err_response(MSG_STATUS_FILTER_INVALID)
            qs = qs.filter(status=raw_status)

        q = (request.query_params.get("search") or "").strip()
        if q:
            qs = qs.filter(
                Q(receipt_id__icontains=q)
                | Q(customer_name__icontains=q)
                | Q(customer_matri__icontains=q)
            )

        raw_date = (request.query_params.get("date") or "").strip()
        if raw_date:
            try:
                d = datetime.strptime(raw_date, "%Y-%m-%d").date()
                qs = qs.filter(created_at__date=d)
            except ValueError:
                pass

        qs = qs.order_by("-created_at")
        paginator = StaffPaymentPagination()
        page = paginator.paginate_queryset(qs, request)
        rows = page if page is not None else list(qs)
        results = [_serialize_row(e, request) for e in rows]
        if page is not None:
            body = paginator.get_paginated_response(results).data
            return Response({"success": True, "data": body})
        return Response(
            {"success": True, "data": {"count": len(results), "results": results}}
        )

    def post(self, request):
        staff_admin, err = _resolve_staff(request)
        if err:
            return err
        staff_profile: StaffProfile = staff_profile_for_dashboard(staff_admin)
        serializer = StaffPaymentCreateSerializer(data=request.data or {})
        try:
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError as e:
            payload = e.detail if isinstance(e.detail, dict) else {}
            if isinstance(payload.get("code"), list):
                code = str(payload.get("code")[0])
            else:
                code = str(payload.get("code", "VALIDATION_ERROR"))
            if isinstance(payload.get("message"), list):
                message = str(payload.get("message")[0])
            else:
                message = str(payload.get("message", "Invalid request data."))
            return _err_response_code(code, message, 400)

        data = serializer.validated_data
        mode = data["mode"]
        customer: User = data["customer"]
        plan = data["plan"]
        amt: Decimal = data["amount"]
        reference_no = data.get("reference_no", "")
        physical_receipt_no = data.get("physical_receipt_no", "")
        cashier_receipt_no = data.get("cashier_receipt_no", "")
        otp = data.get("otp", "")
        notes = data.get("notes", "")
        matri = data["customer_matri_id"]

        if not CustomerStaffAssignment.objects.filter(user=customer, staff=staff_profile).exists():
            return _err_response_code("CUSTOMER_NOT_FOUND", "Customer not found.", 404)

        if mode == PaymentEntry.MODE_CASH:
            ok, otp_message = validate_otp(phone_number=(customer.mobile or "").strip(), otp=otp)
            if not ok:
                err_code = "INVALID_OTP"
                msg_lower = (otp_message or "").lower()
                if "expired" in msg_lower:
                    err_code = "OTP_EXPIRED"
                elif "attempt" in msg_lower:
                    err_code = "OTP_ATTEMPTS_EXCEEDED"
                return _err_response_code(err_code, otp_message, 400)

        receipt_id = generate_receipt_no()
        now = timezone.now()
        sub_payment_mode = "cash" if mode == PaymentEntry.MODE_CASH else "upi"
        payment_reference = reference_no or cashier_receipt_no or physical_receipt_no
        try:
            with db_transaction.atomic():
                txn = record_staff_plan_purchase(
                    customer=customer,
                    plan=plan,
                    payment_mode=sub_payment_mode,
                    payment_reference=payment_reference,
                    amount=amt,
                )
                entry = PaymentEntry.objects.create(
                    receipt_id=receipt_id,
                    staff=staff_admin,
                    branch=staff_profile.branch,
                    customer_matri=customer.matri_id or matri,
                    customer_name=(customer.name or "").strip() or matri,
                    plan=plan,
                    amount=amt,
                    mode=mode,
                    reference_no=reference_no,
                    physical_receipt_no=physical_receipt_no,
                    cashier_receipt_no=cashier_receipt_no,
                    notes=notes,
                    status=PaymentEntry.STATUS_VERIFIED,
                    is_verified=True,
                    verified_at=now,
                    verified_by=staff_admin,
                    transaction=txn,
                )
        except ValueError as e:
            return _err_response_code("INVALID_AMOUNT", str(e), 400)
        # UPI and cash (with OTP) are verified at creation in staff flow.
        create_audit_log(
            request,
            action=AuditLog.ACTION_PAYMENT_CREATE,
            resource=f"payment:{entry.id}",
            details=f"Payment created ₹{entry.amount} via {entry.mode}.",
        )

        return Response(
            {
                "success": True,
                "message": "Payment completed successfully",
                "data": {
                    "payment_id": entry.id,
                    "receipt_no": entry.receipt_id,
                    "status": entry.status,
                    "mode": entry.mode,
                    "amount": float(entry.amount),
                    "is_verified": bool(entry.is_verified),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class StaffPaymentDetailView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, receipt_id: str):
        staff_admin, err = _resolve_staff(request)
        if err:
            return err
        rid = (receipt_id or "").strip()
        entry = _staff_entries(staff_admin).filter(receipt_id__iexact=rid).first()
        if not entry:
            return _err_response(MSG_NOT_FOUND, 404)
        return Response({"success": True, "data": _serialize_detail(entry, request)})


class StaffPaymentReceiptPdfView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, receipt_id: str):
        staff_admin, err = _resolve_staff(request)
        if err:
            return err
        rid = (receipt_id or "").strip()
        entry = _staff_entries(staff_admin).filter(receipt_id__iexact=rid).first()
        if not entry:
            return _err_response(MSG_NOT_FOUND, 404)
        lines = [
            "Aiswarya Matrimony — Payment receipt",
            f"Receipt: {entry.receipt_id}",
            f"Customer: {entry.customer_name} ({entry.customer_matri})",
            f"Plan: {entry.plan.name if entry.plan_id else '-'}",
            f"Amount: Rs. {entry.amount}",
            f"Mode: {_mode_badge(entry.mode)}",
            f"Reference: {entry.reference_no or '-'}",
            f"Status: {entry.status}",
            f"Date: {timezone.localtime(entry.created_at).strftime('%Y-%m-%d %H:%M')}",
        ]
        if entry.notes:
            lines.append(f"Notes: {entry.notes}")
        pdf = _build_simple_pdf(lines)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{entry.receipt_id}.pdf"'
        return response


class BranchPaymentVerifyAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, receipt_id: str):
        branch_manager, err = _resolve_branch_manager(request)
        if err:
            return err
        rid = (receipt_id or "").strip()
        entry = _branch_entries(branch_manager).filter(receipt_id__iexact=rid).first()
        if not entry:
            return _err_response(MSG_NOT_FOUND, 404)
        if entry.status != PaymentEntry.STATUS_PENDING:
            return _err_response(MSG_ONLY_PENDING_VERIFY, 400)
        if not entry.plan_id:
            return _err_response(MSG_PLAN_INVALID, 400)

        customer = User.objects.filter(matri_id__iexact=entry.customer_matri, role="user").first()
        if not customer:
            return _err_response(MSG_CUSTOMER_NOT_FOUND, 404)

        sub_payment_mode = "cash" if entry.mode == PaymentEntry.MODE_CASH else "upi"
        try:
            with db_transaction.atomic():
                txn = record_staff_plan_purchase(
                    customer=customer,
                    plan=entry.plan,
                    payment_mode=sub_payment_mode,
                    payment_reference=entry.reference_no,
                    amount=entry.amount,
                )
                entry.status = PaymentEntry.STATUS_VERIFIED
                entry.is_verified = True
                entry.verified_by = branch_manager
                entry.verified_at = timezone.now()
                entry.transaction = txn
                entry.save(
                    update_fields=[
                        "status",
                        "is_verified",
                        "verified_by",
                        "verified_at",
                        "transaction",
                    ]
                )
        except ValueError as e:
            return _err_response(str(e), 400)

        return Response(
            {
                "success": True,
                "message": "Payment verified successfully.",
                "data": _serialize_detail(entry, request),
            }
        )


class BranchPaymentCompleteAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, receipt_id: str):
        branch_manager, err = _resolve_branch_manager(request)
        if err:
            return err
        rid = (receipt_id or "").strip()
        entry = _branch_entries(branch_manager).filter(receipt_id__iexact=rid).first()
        if not entry:
            return _err_response(MSG_NOT_FOUND, 404)
        if entry.status != PaymentEntry.STATUS_VERIFIED:
            return _err_response(MSG_ONLY_VERIFIED_COMPLETE, 400)
        entry.status = PaymentEntry.STATUS_COMPLETED
        entry.save(update_fields=["status"])
        return Response(
            {
                "success": True,
                "message": "Payment marked as completed.",
                "data": _serialize_detail(entry, request),
            }
        )
