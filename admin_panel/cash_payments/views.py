import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO

from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from admin_panel.audit_log.models import AuditLog
from admin_panel.audit_log.utils import create_audit_log
from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.commissions.models import Commission
from admin_panel.pagination import StandardPagination
from admin_panel.staff_mgmt.models import StaffProfile
from admin_panel.staff_payments.models import PaymentEntry
from plans.models import Plan, Transaction, UserPlan

from .models import PaymentReview
from .serializers import PaymentDetailSerializer, PaymentTableSerializer, payment_mode_label, payment_status_label


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
    mobile = (getattr(user, "mobile", "") or "").strip()
    mobile10 = mobile[-10:] if mobile.startswith("+91") else mobile
    return StaffProfile.objects.filter(mobile=mobile10, is_deleted=False).first()


def _base_queryset():
    return Transaction.objects.filter(transaction_type=Transaction.TYPE_PLAN_PURCHASE).select_related(
        "user",
        "user__branch",
        "user__staff_assignment",
        "user__staff_assignment__staff",
        "plan",
        "payment_review",
    )


def _scoped_queryset(request):
    qs = _base_queryset()
    role = getattr(request.user, "role", None)
    if role == AdminUser.ROLE_BRANCH_MANAGER:
        branch_id = getattr(request.user, "branch_id", None)
        qs = qs.filter(user__branch_id=branch_id) if branch_id else qs.none()
    elif role == AdminUser.ROLE_STAFF:
        staff = _staff_profile_for_admin_user(request.user)
        qs = qs.filter(user__staff_assignment__staff=staff) if staff else qs.none()
    return qs


def _apply_filters(request, qs, apply_date=True):
    mode = (request.query_params.get("mode") or "").strip().lower()
    if mode:
        if mode not in {"cash", "upi", "card", "netbanking"}:
            return None, Response(
                {"success": False, "error": {"code": 400, "message": "Invalid payment mode filter"}},
                status=400,
            )
        if mode == "cash":
            qs = qs.filter(payment_method=Transaction.PAYMENT_MANUAL)
        elif mode == "upi":
            qs = qs.filter(payment_method=Transaction.PAYMENT_UPI)
        elif mode == "card":
            qs = qs.filter(payment_method__in=[Transaction.PAYMENT_RAZORPAY, Transaction.PAYMENT_STRIPE]).exclude(
                Q(transaction_id__icontains="netbank") | Q(transaction_id__icontains="bank")
            )
        else:
            qs = qs.filter(payment_method__in=[Transaction.PAYMENT_RAZORPAY, Transaction.PAYMENT_STRIPE]).filter(
                Q(transaction_id__icontains="netbank") | Q(transaction_id__icontains="bank")
            )

    role = getattr(request.user, "role", None)
    branch_id = request.query_params.get("branch_id")
    if branch_id:
        if role == AdminUser.ROLE_BRANCH_MANAGER and int(branch_id) != int(getattr(request.user, "branch_id", 0) or 0):
            return None, Response({"success": False, "error": {"code": 403, "message": "Access denied"}}, status=403)
        qs = qs.filter(user__branch_id=branch_id)

    staff_id = request.query_params.get("staff_id")
    if staff_id:
        qs = qs.filter(user__staff_assignment__staff_id=staff_id)

    status_filter = (request.query_params.get("status") or "").strip().lower()
    if status_filter:
        if status_filter == "verified":
            qs = qs.filter(payment_status=Transaction.STATUS_SUCCESS)
        elif status_filter == "pending":
            qs = qs.filter(payment_status=Transaction.STATUS_PENDING)
        elif status_filter == "rejected":
            qs = qs.filter(payment_status__in=[Transaction.STATUS_FAILED, Transaction.STATUS_REFUNDED])
        else:
            return None, Response({"success": False, "error": {"code": 400, "message": "Invalid status filter"}}, status=400)

    search = (request.query_params.get("search") or "").strip()
    if search:
        qs = qs.filter(
            Q(transaction_id__icontains=search) | Q(user__name__icontains=search) | Q(user__matri_id__icontains=search)
        )

    if apply_date:
        date_s = (request.query_params.get("date") or "").strip()
        if date_s:
            try:
                d = datetime.strptime(date_s, "%Y-%m-%d").date()
            except ValueError:
                return None, Response({"success": False, "error": {"code": 400, "message": "Invalid date filter"}}, status=400)
            qs = qs.filter(created_at__date=d)
    return qs, None


class PaymentsListAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            self._paginator = self.pagination_class() if self.pagination_class else None
        return self._paginator

    def get(self, request):
        qs = _scoped_queryset(request)
        qs, err = _apply_filters(request, qs)
        if err:
            return err
        qs = qs.order_by("-created_at")
        page = self.paginator.paginate_queryset(qs, request, view=self) if self.paginator else None
        ser = PaymentTableSerializer(page if page is not None else qs, many=True)
        if page is not None:
            paged = self.paginator.get_paginated_response(ser.data)
            return Response({"success": True, "data": paged.data})
        return Response({"success": True, "data": {"count": len(ser.data), "results": ser.data}})

    def post(self, request):
        matri_id = (request.data.get("customer_matri_id") or "").strip()
        if not matri_id:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Customer matri_id is required"}},
                status=400,
            )
        user = User.objects.filter(matri_id__iexact=matri_id, is_active=True).first()
        if not user:
            return Response({"success": False, "error": {"code": 404, "message": "Customer not found"}}, status=404)

        plan_id = request.data.get("plan_id")
        plan = Plan.objects.filter(pk=plan_id, is_active=True).first()
        if not plan:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Invalid or inactive plan"}},
                status=400,
            )
        try:
            amount = Decimal(str(request.data.get("amount")))
        except Exception:
            amount = None
        if amount is None or amount != Decimal(plan.price):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": 400,
                        "message": f"Amount must equal plan price ({plan.price})",
                    },
                },
                status=400,
            )
        txid = (request.data.get("receipt_txn_id") or "").strip() or f"CASH-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        txn = Transaction.objects.create(
            user=user,
            plan=plan,
            amount=amount,
            service_charge=Decimal("0"),
            total_amount=amount,
            payment_method=Transaction.PAYMENT_MANUAL,
            payment_status=Transaction.STATUS_PENDING,
            transaction_type=Transaction.TYPE_PLAN_PURCHASE,
            transaction_id=txid,
        )
        return Response({"success": True, "data": PaymentDetailSerializer(txn).data}, status=201)


class PaymentsSummaryAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = _scoped_queryset(request)
        qs, err = _apply_filters(request, qs, apply_date=False)
        if err:
            return err

        today = timezone.localdate()
        ref = today
        date_s = (request.query_params.get("date") or "").strip()
        if date_s:
            try:
                ref = datetime.strptime(date_s, "%Y-%m-%d").date()
            except ValueError:
                ref = today
        prev = ref - timedelta(days=1)
        current_qs = qs.filter(created_at__date=ref)
        prev_qs = qs.filter(created_at__date=prev)

        def _metrics(mode: str):
            def _mode(q):
                if mode == "cash":
                    return q.filter(payment_method=Transaction.PAYMENT_MANUAL)
                if mode == "upi":
                    return q.filter(payment_method=Transaction.PAYMENT_UPI)
                if mode == "card":
                    return q.filter(payment_method__in=[Transaction.PAYMENT_RAZORPAY, Transaction.PAYMENT_STRIPE]).exclude(
                        Q(transaction_id__icontains="netbank") | Q(transaction_id__icontains="bank")
                    )
                return q

            a = _mode(current_qs)
            b = _mode(prev_qs)
            total = Decimal(a.aggregate(v=Sum("total_amount"))["v"] or 0)
            count = a.count()
            prev_total = Decimal(b.aggregate(v=Sum("total_amount"))["v"] or 0)
            growth = float(((total - prev_total) / prev_total) * 100) if prev_total else (100.0 if total else 0.0)
            return {"total": float(total), "count": count, "growth_percent": round(growth, 2)}

        cash = _metrics("cash")
        upi = _metrics("upi")
        card = _metrics("card")
        total = Decimal(current_qs.aggregate(v=Sum("total_amount"))["v"] or 0)
        prev_total = Decimal(prev_qs.aggregate(v=Sum("total_amount"))["v"] or 0)
        tg = float(((total - prev_total) / prev_total) * 100) if prev_total else (100.0 if total else 0.0)
        out = {
            "live": True,
            "last_updated": timezone.now().isoformat(),
            "cash_payments": cash,
            "upi_payments": upi,
            "card_payments": card,
            "total_revenue": {"total": float(total), "count": current_qs.count(), "growth_percent": round(tg, 2)},
        }
        return Response({"success": True, "data": out})


class PaymentDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        qs = _scoped_queryset(request)
        obj = qs.filter(pk=pk).first()
        if not obj:
            return Response({"success": False, "error": {"code": 404, "message": "Payment not found"}}, status=404)
        return Response({"success": True, "data": PaymentDetailSerializer(obj).data})


class VerifyPaymentAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        obj = _scoped_queryset(request).filter(pk=pk).first()
        if not obj:
            return Response({"success": False, "error": {"code": 404, "message": "Payment not found"}}, status=404)
        if payment_mode_label(obj) != "cash":
            return Response(
                {"success": False, "error": {"code": 400, "message": "Only cash payments require manual verification"}},
                status=400,
            )
        if payment_status_label(obj) != "pending":
            return Response(
                {"success": False, "error": {"code": 400, "message": "Payment already verified or rejected"}},
                status=400,
            )
        obj.payment_status = Transaction.STATUS_SUCCESS
        obj.save(update_fields=["payment_status", "updated_at"])
        PaymentReview.objects.update_or_create(
            transaction=obj,
            defaults={"reviewed_by": request.user, "reviewed_at": timezone.now(), "rejection_reason": ""},
        )
        return Response({"success": True, "data": PaymentDetailSerializer(obj).data})


class RejectPaymentAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Rejection reason is required"}},
                status=400,
            )
        obj = _scoped_queryset(request).filter(pk=pk).first()
        if not obj:
            return Response({"success": False, "error": {"code": 404, "message": "Payment not found"}}, status=404)
        obj.payment_status = Transaction.STATUS_FAILED
        obj.save(update_fields=["payment_status", "updated_at"])
        PaymentReview.objects.update_or_create(
            transaction=obj,
            defaults={"reviewed_by": request.user, "reviewed_at": timezone.now(), "rejection_reason": reason},
        )
        return Response({"success": True, "data": PaymentDetailSerializer(obj).data})


def _void_verified_cash_payment(txn: Transaction) -> dict:
    """
    Remove a verified cash plan purchase from the ledger.
    Deletes the staff payment entry and matching unpaid commissions.
    If this was the customer's only successful plan purchase, removes their UserPlan.
    """
    if payment_mode_label(txn) != "cash":
        raise ValueError("Only cash payments can be voided")
    if payment_status_label(txn) != "verified":
        raise ValueError("Only verified cash payments can be voided")

    user = txn.user
    sale_amount = txn.total_amount
    matching_commissions = Commission.objects.filter(customer=user, sale_amount=sale_amount)
    if txn.plan_id:
        matching_commissions = matching_commissions.filter(
            Q(plan_id=txn.plan_id) | Q(subscription__plan_id=txn.plan_id)
        )

    remaining_success = (
        Transaction.objects.filter(
            user=user,
            transaction_type=Transaction.TYPE_PLAN_PURCHASE,
            payment_status=Transaction.STATUS_SUCCESS,
        )
        .exclude(pk=txn.pk)
        .exists()
    )
    user_plan = UserPlan.objects.filter(user=user).first()
    if not remaining_success and user_plan:
        if Commission.objects.filter(subscription=user_plan, status=Commission.STATUS_PAID).exists():
            raise ValueError("Cannot void a payment with a paid commission")
    elif matching_commissions.filter(status=Commission.STATUS_PAID).exists():
        raise ValueError("Cannot void a payment with a paid commission")

    with db_transaction.atomic():
        matching_commissions.exclude(status=Commission.STATUS_PAID).delete()
        PaymentEntry.objects.filter(transaction=txn).delete()
        PaymentReview.objects.filter(transaction=txn).delete()
        txn.delete()
        plan_removed = False
        if not remaining_success:
            leftover = UserPlan.objects.filter(user=user).first()
            if leftover:
                Commission.objects.filter(subscription=leftover).delete()
                leftover.delete()
                plan_removed = True
        return {"removed": True, "plan_removed": plan_removed}


class VoidPaymentAPIView(APIView):
    """PATCH /api/v1/admin/payments/{id}/void/ — admin-only removal of a verified cash payment."""

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if getattr(request.user, "role", None) != AdminUser.ROLE_ADMIN:
            return Response(
                {"success": False, "error": {"code": 403, "message": "Only admin can void payments"}},
                status=403,
            )
        obj = _scoped_queryset(request).filter(pk=pk).first()
        if not obj:
            return Response({"success": False, "error": {"code": 404, "message": "Payment not found"}}, status=404)
        receipt = obj.transaction_id or ""
        customer_name = (getattr(obj.user, "name", "") or "").strip()
        try:
            result = _void_verified_cash_payment(obj)
        except ValueError as exc:
            return Response(
                {"success": False, "error": {"code": 400, "message": str(exc)}},
                status=400,
            )
        create_audit_log(
            request,
            action=AuditLog.ACTION_DELETE,
            resource=f"payment:{pk}",
            details=f"Voided cash payment #{pk} ({receipt}).",
            target_profile_name=customer_name,
        )
        return Response({"success": True, "data": {"id": pk, **result}})


class PaymentsExportCSVAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = _scoped_queryset(request)
        qs, err = _apply_filters(request, qs)
        if err:
            return err
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="payments_export.csv"'
        writer = csv.writer(response)
        writer.writerow(
            ["Time", "Receipt/TXN ID", "Customer", "Matri ID", "Plan", "Amount", "Mode", "Branch", "Staff", "Status"]
        )
        for obj in qs.order_by("-created_at").iterator(chunk_size=500):
            asn = getattr(obj.user, "staff_assignment", None)
            writer.writerow(
                [
                    obj.created_at.strftime("%I:%M %p"),
                    obj.transaction_id or f"PAY-{obj.id:06d}",
                    obj.user.name or "",
                    obj.user.matri_id or "",
                    obj.plan.name if obj.plan_id else "",
                    str(obj.total_amount),
                    payment_mode_label(obj),
                    obj.user.branch.name if obj.user.branch_id else "",
                    asn.staff.name if asn and asn.staff else "",
                    payment_status_label(obj),
                ]
            )
        return response


class PaymentsPDFReportAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = _scoped_queryset(request)
        qs, err = _apply_filters(request, qs)
        if err:
            return err
        qs = qs.order_by("-created_at")[:50]
        lines = ["Payment Report", f"Generated: {timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')}"]
        for obj in qs:
            lines.append(
                f"{obj.created_at.strftime('%H:%M')} | {obj.transaction_id or obj.id} | {obj.user.name} | {obj.total_amount} | {payment_mode_label(obj)} | {payment_status_label(obj)}"
            )
        pdf = _build_simple_pdf(lines)
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = 'attachment; filename="payments_report.pdf"'
        return resp
