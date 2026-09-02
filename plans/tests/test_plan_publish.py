from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch as PanelBranch
from admin_panel.staff_mgmt.models import StaffProfile
from master.models import Branch as MasterBranch
from plans.models import Plan


LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "plan-publish-tests",
    }
}


def _plan(**kwargs):
    defaults = dict(
        price=Decimal("499"),
        duration_days=30,
        profile_view_limit=10,
        interest_limit=5,
        chat_limit=5,
        contact_view_limit=5,
        horoscope_match_limit=0,
        is_active=True,
        is_published=True,
    )
    defaults.update(kwargs)
    return Plan.objects.create(**defaults)


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    CACHES=LOCMEM_CACHES,
)
class PlanPublishVisibilityTests(TestCase):
    def setUp(self):
        self.public_plan = _plan(name="Gold Public")
        self.internal_plan = _plan(name="Registration Fee Internal", is_published=False)
        self.inactive_plan = _plan(name="Old Inactive", is_active=False, is_published=True)

        self.member = User.objects.create_user(
            mobile="+919876543210",
            password="x",
            name="Member",
            gender="M",
            role="user",
        )
        self.member.is_active = True
        self.member.save(update_fields=["is_active"])

        self.admin = AdminUser.objects.create(
            mobile="+919900000401",
            role=AdminUser.ROLE_ADMIN,
            name="Plans Admin",
            is_active=True,
        )

        self.master_br = MasterBranch.objects.create(name="Publish Branch", code="PUB_01")
        self.panel_br = PanelBranch.objects.create(
            name="Publish Branch Panel",
            code="PUB_01",
            city="City",
            phone="9999999901",
            email="pub_01@test.invalid",
        )
        self.staff_admin = AdminUser.objects.create(
            mobile="9000000402",
            name="Pay Staff",
            role=AdminUser.ROLE_STAFF,
            branch_id=self.master_br.pk,
            is_active=True,
        )
        StaffProfile.objects.create(
            admin_user=self.staff_admin,
            name="Pay Staff Person",
            mobile="8000000402",
            email="pay_staff_pub@test.invalid",
            branch=self.panel_br,
            designation="Executive",
            department="Sales",
        )

        self.client = APIClient()

    def _ids(self, plans):
        return {row["id"] for row in plans}

    def test_website_plans_omit_unpublished(self):
        res = self.client.get("/api/v1/website/plans/")
        self.assertEqual(res.status_code, 200, res.data)
        ids = self._ids(res.data["data"]["plans"])
        self.assertIn(self.public_plan.id, ids)
        self.assertNotIn(self.internal_plan.id, ids)
        self.assertNotIn(self.inactive_plan.id, ids)

    def test_member_plans_omit_unpublished(self):
        self.client.force_authenticate(user=self.member)
        res = self.client.get("/api/v1/plans/")
        self.assertEqual(res.status_code, 200, res.data)
        ids = self._ids(res.data["data"]["plans"])
        self.assertIn(self.public_plan.id, ids)
        self.assertNotIn(self.internal_plan.id, ids)
        self.assertNotIn(self.inactive_plan.id, ids)

    def test_online_order_rejects_unpublished_plan(self):
        self.client.force_authenticate(user=self.member)
        res = self.client.post(
            "/api/v1/plans/order/",
            {"plan_id": self.internal_plan.id, "payment_option": "plan_only"},
            format="json",
        )
        self.assertEqual(res.status_code, 400, res.data)
        self.assertFalse(res.data.get("success"))

    def test_online_purchase_rejects_unpublished_plan(self):
        self.client.force_authenticate(user=self.member)
        res = self.client.post(
            "/api/v1/plans/purchase/",
            {
                "plan_id": self.internal_plan.id,
                "payment_method": "manual",
                "payment_option": "plan_only",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400, res.data)
        self.assertFalse(res.data.get("success"))

    def test_admin_toggle_publish(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(
            f"/api/v1/admin/plans/{self.internal_plan.id}/toggle-publish/",
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data["success"])
        self.assertTrue(res.data["data"]["is_published"])
        self.assertEqual(res.data["data"]["status"], "published")
        self.internal_plan.refresh_from_db()
        self.assertTrue(self.internal_plan.is_published)

        res = self.client.patch(
            f"/api/v1/admin/plans/{self.internal_plan.id}/toggle-publish/",
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertFalse(res.data["data"]["is_published"])
        self.assertEqual(res.data["data"]["status"], "unpublished")

    def test_staff_cannot_toggle_publish(self):
        self.client.force_authenticate(user=self.staff_admin)
        res = self.client.patch(
            f"/api/v1/admin/plans/{self.public_plan.id}/toggle-publish/",
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_staff_plans_list_includes_unpublished_active(self):
        self.client.force_authenticate(user=self.staff_admin)
        res = self.client.get("/api/v1/staff/payments/plans/")
        self.assertEqual(res.status_code, 200, res.data)
        ids = self._ids(res.data["data"]["results"])
        self.assertIn(self.public_plan.id, ids)
        self.assertIn(self.internal_plan.id, ids)
        self.assertNotIn(self.inactive_plan.id, ids)

    def test_staff_quote_accepts_unpublished_active_plan(self):
        self.client.force_authenticate(user=self.staff_admin)
        res = self.client.post(
            "/api/v1/staff/payments/quote/",
            {"plan_id": self.internal_plan.id, "discount_amount": "0"},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data.get("success"))
        self.assertEqual(res.data["data"]["plan_id"], self.internal_plan.id)

    def test_admin_plan_list_includes_is_published(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/admin/plans/")
        self.assertEqual(res.status_code, 200, res.data)
        by_id = {row["id"]: row for row in res.data["data"]}
        self.assertTrue(by_id[self.public_plan.id]["is_published"])
        self.assertFalse(by_id[self.internal_plan.id]["is_published"])
