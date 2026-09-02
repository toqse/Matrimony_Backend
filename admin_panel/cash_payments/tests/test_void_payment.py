from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from admin_panel.auth.models import AdminUser
from admin_panel.staff_payments.models import PaymentEntry
from admin_panel.branches.models import Branch as PanelBranch
from plans.models import Plan, Transaction, UserPlan


LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "void-payment-tests",
    }
}


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    CACHES=LOCMEM_CACHES,
)
class VoidVerifiedCashPaymentTests(TestCase):
    def setUp(self):
        self.admin = AdminUser.objects.create(
            mobile="+919900000501",
            role=AdminUser.ROLE_ADMIN,
            name="Void Admin",
            is_active=True,
        )
        self.staff = AdminUser.objects.create(
            mobile="+919900000502",
            role=AdminUser.ROLE_STAFF,
            name="Void Staff",
            is_active=True,
        )
        self.customer = User.objects.create_user(
            mobile="+919876540501",
            password="x",
            name="John Doert",
            gender="M",
            role="user",
        )
        self.plan = Plan.objects.create(
            name="REGISTRATION FEE",
            price=Decimal("1500"),
            duration_days=30,
            is_active=True,
            is_published=False,
        )
        today = timezone.localdate()
        self.user_plan = UserPlan.objects.create(
            user=self.customer,
            plan=self.plan,
            price_paid=Decimal("1500"),
            is_active=True,
            valid_from=today,
            valid_until=today + timedelta(days=30),
        )
        self.txn = Transaction.objects.create(
            user=self.customer,
            plan=self.plan,
            amount=Decimal("1500"),
            service_charge=Decimal("0"),
            total_amount=Decimal("1500"),
            payment_method=Transaction.PAYMENT_MANUAL,
            payment_status=Transaction.STATUS_SUCCESS,
            transaction_type=Transaction.TYPE_PLAN_PURCHASE,
            transaction_id="514errrrrrr",
        )
        self.branch = PanelBranch.objects.create(
            name="Alappuzha",
            code="ALP_VOID",
            city="Alappuzha",
            phone="9999999501",
            email="alp_void@test.invalid",
        )
        PaymentEntry.objects.create(
            receipt_id="RCP-VOID-001",
            staff=self.staff,
            branch=self.branch,
            customer_matri=self.customer.matri_id or "AM121103",
            customer_name="John Doert",
            plan=self.plan,
            amount=Decimal("1500"),
            mode=PaymentEntry.MODE_CASH,
            status=PaymentEntry.STATUS_VERIFIED,
            is_verified=True,
            transaction=self.txn,
        )
        self.client = APIClient()

    def test_admin_voids_verified_cash_payment_and_plan(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(f"/api/v1/admin/payments/{self.txn.id}/void/", format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data["success"])
        self.assertTrue(res.data["data"]["removed"])
        self.assertTrue(res.data["data"]["plan_removed"])
        self.assertFalse(Transaction.objects.filter(pk=self.txn.id).exists())
        self.assertFalse(UserPlan.objects.filter(user=self.customer).exists())
        self.assertFalse(PaymentEntry.objects.filter(receipt_id="RCP-VOID-001").exists())

    def test_staff_cannot_void(self):
        self.client.force_authenticate(user=self.staff)
        res = self.client.patch(f"/api/v1/admin/payments/{self.txn.id}/void/", format="json")
        self.assertEqual(res.status_code, 403)
        self.assertTrue(Transaction.objects.filter(pk=self.txn.id).exists())

    def test_pending_cash_cannot_be_voided(self):
        self.txn.payment_status = Transaction.STATUS_PENDING
        self.txn.save(update_fields=["payment_status"])
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(f"/api/v1/admin/payments/{self.txn.id}/void/", format="json")
        self.assertEqual(res.status_code, 400, res.data)
        self.assertIn("verified", res.data["error"]["message"].lower())

    def test_upi_payment_cannot_be_voided(self):
        self.txn.payment_method = Transaction.PAYMENT_UPI
        self.txn.save(update_fields=["payment_method"])
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(f"/api/v1/admin/payments/{self.txn.id}/void/", format="json")
        self.assertEqual(res.status_code, 400, res.data)
        self.assertIn("cash", res.data["error"]["message"].lower())

    def test_void_keeps_plan_when_other_success_purchase_exists(self):
        Transaction.objects.create(
            user=self.customer,
            plan=self.plan,
            amount=Decimal("1500"),
            total_amount=Decimal("1500"),
            payment_method=Transaction.PAYMENT_RAZORPAY,
            payment_status=Transaction.STATUS_SUCCESS,
            transaction_type=Transaction.TYPE_PLAN_PURCHASE,
            transaction_id="rzp_other",
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(f"/api/v1/admin/payments/{self.txn.id}/void/", format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertFalse(res.data["data"]["plan_removed"])
        self.assertTrue(UserPlan.objects.filter(user=self.customer).exists())
        self.assertFalse(Transaction.objects.filter(pk=self.txn.id).exists())
