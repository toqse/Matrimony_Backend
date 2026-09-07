from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from admin_panel.staff_subscriptions.services import (
    record_staff_plan_purchase,
    staff_subscription_same_plan_active_preflight,
)
from plans.models import Plan, ServiceCharge, Transaction, UserPlan
from plans.services import (
    activate_plan_purchase,
    get_plan_info_for_response,
)


LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "same-plan-purchase-tests",
    }
}


@override_settings(
    CACHES=LOCMEM_CACHES,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_BROKER_URL="memory://",
    CELERY_RESULT_BACKEND=None,
)
class SamePlanPurchaseTests(TestCase):
    def setUp(self):
        self._wa_patcher = patch(
            "notifications.whatsapp_notify.enqueue_subscription_confirmation",
            return_value=None,
        )
        self._wa_patcher.start()
        self.addCleanup(self._wa_patcher.stop)
        self.user = User.objects.create_user(
            mobile="+919876543901",
            password="x",
            name="Plan Member",
            gender="M",
            role="user",
        )
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        ServiceCharge.objects.update_or_create(
            gender="M", defaults={"amount": Decimal("15000")}
        )
        self.gold = Plan.objects.create(
            name="Gold",
            price=Decimal("499"),
            duration_days=30,
            profile_view_limit=10,
            interest_limit=5,
            chat_limit=5,
            contact_view_limit=5,
            horoscope_match_limit=3,
            is_active=True,
            is_published=True,
        )
        self.diamond = Plan.objects.create(
            name="Diamond",
            price=Decimal("999"),
            duration_days=90,
            profile_view_limit=30,
            interest_limit=15,
            chat_limit=15,
            contact_view_limit=15,
            horoscope_match_limit=10,
            is_active=True,
            is_published=True,
        )
        today = timezone.now().date()
        self.user_plan = UserPlan.objects.create(
            user=self.user,
            plan=self.gold,
            price_paid=Decimal("499"),
            service_charge=Decimal("15000"),
            service_charge_paid=Decimal("499"),
            is_active=True,
            valid_from=today,
            valid_until=today + timedelta(days=30),
            profile_views_used=3,
            contact_views_used=5,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_order_allows_active_same_plan(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "id": "order_same_plan_1",
            "amount": 49900,
            "currency": "INR",
            "receipt": "plsameplan",
        }
        with override_settings(
            RAZORPAY_KEY_ID="rzp_test_key",
            RAZORPAY_KEY_SECRET="rzp_test_secret",
        ), patch("plans.razorpay_client.requests.post", return_value=mock_resp):
            res = self.client.post(
                "/api/v1/plans/order/",
                {"plan_id": self.gold.id, "payment_option": "plan_only"},
                format="json",
            )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data.get("success"))
        self.assertEqual(res.data["data"]["plan_id"], self.gold.id)

    def test_purchase_allows_active_same_plan(self):
        original_until = self.user_plan.valid_until
        res = self.client.post(
            "/api/v1/plans/purchase/",
            {
                "plan_id": self.gold.id,
                "payment_method": Transaction.PAYMENT_MANUAL,
                "payment_option": "plan_only",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data.get("success"))
        self.assertIn("additional credits", (res.data.get("message") or "").lower())
        self.user_plan.refresh_from_db()
        self.assertEqual(self.user_plan.plan_id, self.gold.id)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)
        self.assertEqual(
            self.user_plan.valid_until,
            original_until + timedelta(days=self.gold.duration_days),
        )

    def test_activate_same_plan_tops_up_exhausted_contact_views(self):
        today = timezone.now().date()
        original_until = self.user_plan.valid_until
        _, txn, extra = activate_plan_purchase(
            user=self.user,
            plan=self.gold,
            payment_option="plan_only",
            payment_method=Transaction.PAYMENT_MANUAL,
        )
        self.user_plan.refresh_from_db()
        self.assertEqual(self.user_plan.plan_id, self.gold.id)
        self.assertEqual(self.user_plan.contact_views_used, 0)
        self.assertEqual(extra["carry_forward"]["contacts"], 0)
        self.assertEqual(extra["carry_forward"]["profile_views"], 7)
        self.assertEqual(
            self.user_plan.valid_until,
            original_until + timedelta(days=self.gold.duration_days),
        )
        self.assertIn("additional credits", extra["message"].lower())
        info = get_plan_info_for_response(self.user)
        self.assertEqual(info["contact_view_remaining"], self.gold.contact_view_limit)
        self.assertEqual(info["profile_views_remaining"], 17)
        self.assertEqual(txn.plan_id, self.gold.id)
        self.assertEqual(self.user_plan.valid_from, today)

    def test_upgrade_to_different_plan_succeeds(self):
        _, txn, extra = activate_plan_purchase(
            user=self.user,
            plan=self.diamond,
            payment_option="plan_only",
            payment_method=Transaction.PAYMENT_MANUAL,
        )
        self.user_plan.refresh_from_db()
        self.assertEqual(self.user_plan.plan_id, self.diamond.id)
        self.assertTrue(self.user_plan.is_active)
        self.assertEqual(extra["carry_forward"]["profile_views"], 7)
        self.assertEqual(txn.plan_id, self.diamond.id)
        self.assertIn("upgraded", extra["message"].lower())

    def test_repurchase_preserves_service_charge_paid(self):
        self.user_plan.service_charge_paid = Decimal("15000")
        self.user_plan.save(update_fields=["service_charge_paid", "updated_at"])

        activate_plan_purchase(
            user=self.user,
            plan=self.gold,
            payment_option="plan_only",
            payment_method=Transaction.PAYMENT_MANUAL,
        )
        self.user_plan.refresh_from_db()
        self.assertEqual(self.user_plan.service_charge_paid, Decimal("15000"))
        self.assertEqual(self.user_plan.service_charge, Decimal("15000"))
        info = get_plan_info_for_response(self.user)
        self.assertEqual(info["service_charge_paid"], 15000.0)
        self.assertEqual(info["service_charge_remaining"], 0.0)

    def test_repurchase_same_plan_after_expiry_succeeds(self):
        today = timezone.now().date()
        self.user_plan.valid_until = today - timedelta(days=1)
        self.user_plan.save(update_fields=["valid_until", "updated_at"])

        _, txn, extra = activate_plan_purchase(
            user=self.user,
            plan=self.gold,
            payment_option="plan_only",
            payment_method=Transaction.PAYMENT_MANUAL,
        )
        self.user_plan.refresh_from_db()
        self.assertEqual(self.user_plan.plan_id, self.gold.id)
        self.assertTrue(self.user_plan.is_active)
        self.assertEqual(self.user_plan.valid_until, today + timedelta(days=self.gold.duration_days))
        self.assertEqual(extra["carry_forward"]["profile_views"], 0)
        self.assertEqual(txn.plan_id, self.gold.id)

    def test_purchase_same_plan_after_expiry_via_api(self):
        today = timezone.now().date()
        self.user_plan.valid_until = today - timedelta(days=1)
        self.user_plan.save(update_fields=["valid_until", "updated_at"])

        res = self.client.post(
            "/api/v1/plans/purchase/",
            {
                "plan_id": self.gold.id,
                "payment_method": Transaction.PAYMENT_MANUAL,
                "payment_option": "plan_only",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data.get("success"))
        self.user_plan.refresh_from_db()
        self.assertEqual(self.user_plan.plan_id, self.gold.id)
        self.assertTrue(self.user_plan.is_active)

    def test_my_plan_includes_plan_id(self):
        res = self.client.get("/api/v1/my/plan/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["data"]["plan_id"], self.gold.id)
        self.assertEqual(res.data["data"]["plan_name"], "Gold")

        info = get_plan_info_for_response(self.user)
        self.assertEqual(info["plan_id"], self.gold.id)


class StaffSamePlanPurchaseTests(TestCase):
    def setUp(self):
        self._wa_patcher = patch(
            "notifications.whatsapp_notify.enqueue_subscription_confirmation",
            return_value=None,
        )
        self._wa_patcher.start()
        self.addCleanup(self._wa_patcher.stop)
        self.customer = User.objects.create_user(
            mobile="+919876543902",
            password="x",
            name="Staff Customer",
            gender="F",
            role="user",
        )
        ServiceCharge.objects.update_or_create(
            gender="F", defaults={"amount": Decimal("10000")}
        )
        self.gold = Plan.objects.create(
            name="Gold",
            price=Decimal("499"),
            duration_days=30,
            contact_view_limit=5,
            is_active=True,
        )
        today = timezone.now().date()
        self.user_plan = UserPlan.objects.create(
            user=self.customer,
            plan=self.gold,
            price_paid=Decimal("499"),
            service_charge=Decimal("10000"),
            service_charge_paid=Decimal("10000"),
            is_active=True,
            valid_from=today,
            valid_until=today + timedelta(days=30),
            contact_views_used=5,
        )

    def test_staff_preflight_allows_active_same_plan(self):
        msg = staff_subscription_same_plan_active_preflight(self.customer, self.gold)
        self.assertIsNone(msg)

    def test_staff_record_purchase_allows_active_same_plan(self):
        original_until = self.user_plan.valid_until
        txn = record_staff_plan_purchase(
            customer=self.customer,
            plan=self.gold,
            payment_mode="cash",
            payment_reference="CASH-1",
            amount=Decimal("499"),
        )
        self.assertIsNotNone(txn)
        self.assertEqual(Transaction.objects.filter(user=self.customer).count(), 1)
        self.user_plan.refresh_from_db()
        self.assertEqual(self.user_plan.plan_id, self.gold.id)
        self.assertEqual(self.user_plan.contact_views_used, 0)
        self.assertEqual(self.user_plan.contact_view_bonus, 0)
        self.assertEqual(self.user_plan.service_charge_paid, Decimal("10000"))
        self.assertEqual(
            self.user_plan.valid_until,
            original_until + timedelta(days=self.gold.duration_days),
        )
        info = get_plan_info_for_response(self.customer)
        self.assertEqual(info["contact_view_remaining"], self.gold.contact_view_limit)
