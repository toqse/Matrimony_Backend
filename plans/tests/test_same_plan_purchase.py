from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from admin_panel.staff_subscriptions.services import (
    record_staff_plan_purchase,
    staff_subscription_same_plan_active_preflight,
)
from plans.models import Plan, Transaction, UserPlan
from plans.services import (
    ACTIVE_SAME_PLAN,
    SamePlanAlreadyActiveError,
    activate_plan_purchase,
    get_plan_info_for_response,
)


LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "same-plan-purchase-tests",
    }
}


@override_settings(CACHES=LOCMEM_CACHES)
class SamePlanPurchaseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            mobile="+919876543901",
            password="x",
            name="Plan Member",
            gender="M",
            role="user",
        )
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
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
        )
        today = timezone.now().date()
        self.user_plan = UserPlan.objects.create(
            user=self.user,
            plan=self.gold,
            price_paid=Decimal("499"),
            is_active=True,
            valid_from=today,
            valid_until=today + timedelta(days=30),
            profile_views_used=3,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _assert_same_plan_conflict(self, res):
        self.assertEqual(res.status_code, 409, res.data)
        self.assertFalse(res.data.get("success"))
        self.assertEqual(res.data["error"]["code"], ACTIVE_SAME_PLAN)
        self.assertIn("already have an active Gold plan", res.data["error"]["message"])

    def test_order_rejects_active_same_plan(self):
        res = self.client.post(
            "/api/v1/plans/order/",
            {"plan_id": self.gold.id, "payment_option": "plan_only"},
            format="json",
        )
        self._assert_same_plan_conflict(res)

    def test_purchase_rejects_active_same_plan(self):
        res = self.client.post(
            "/api/v1/plans/purchase/",
            {
                "plan_id": self.gold.id,
                "payment_method": Transaction.PAYMENT_MANUAL,
                "payment_option": "plan_only",
            },
            format="json",
        )
        self._assert_same_plan_conflict(res)
        self.user_plan.refresh_from_db()
        self.assertEqual(self.user_plan.plan_id, self.gold.id)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)

    def test_activate_raises_for_active_same_plan(self):
        with self.assertRaises(SamePlanAlreadyActiveError):
            activate_plan_purchase(
                user=self.user,
                plan=self.gold,
                payment_option="plan_only",
                payment_method=Transaction.PAYMENT_MANUAL,
            )

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
        self.customer = User.objects.create_user(
            mobile="+919876543902",
            password="x",
            name="Staff Customer",
            gender="F",
            role="user",
        )
        self.gold = Plan.objects.create(
            name="Gold",
            price=Decimal("499"),
            duration_days=30,
            is_active=True,
        )
        today = timezone.now().date()
        UserPlan.objects.create(
            user=self.customer,
            plan=self.gold,
            price_paid=Decimal("499"),
            is_active=True,
            valid_from=today,
            valid_until=today + timedelta(days=30),
        )

    def test_staff_preflight_blocks_active_same_plan(self):
        msg = staff_subscription_same_plan_active_preflight(self.customer, self.gold)
        self.assertIsNotNone(msg)
        self.assertIn("already has an active Gold plan", msg)
        self.assertIn("Use renew instead", msg)

    def test_staff_record_purchase_raises_for_active_same_plan(self):
        with self.assertRaises(ValueError) as ctx:
            record_staff_plan_purchase(
                customer=self.customer,
                plan=self.gold,
                payment_mode="cash",
                payment_reference="CASH-1",
                amount=Decimal("499"),
            )
        self.assertIn("already has an active Gold plan", str(ctx.exception))
        self.assertEqual(Transaction.objects.filter(user=self.customer).count(), 0)
