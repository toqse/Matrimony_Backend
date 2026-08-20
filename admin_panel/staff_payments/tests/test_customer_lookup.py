from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch as PanelBranch
from admin_panel.staff_mgmt.models import StaffProfile
from master.models import Branch as MasterBranch


class CustomerLookupAPITests(TestCase):
    def setUp(self):
        self.master_br = MasterBranch.objects.create(name="Lookup Branch", code="PAY_LK_01")
        self.panel_br = PanelBranch.objects.create(
            name="Lookup Branch Panel",
            code="PAY_LK_01",
            city="City",
            phone="9999999998",
            email="pay_lk_01@test.invalid",
        )
        self.staff_admin = AdminUser.objects.create(
            mobile="9000000101",
            name="Pay Staff",
            role=AdminUser.ROLE_STAFF,
            branch_id=self.master_br.pk,
        )
        self.staff_profile = StaffProfile.objects.create(
            admin_user=self.staff_admin,
            name="Pay Staff Person",
            mobile="8000000101",
            email="pay_staff_lk@test.invalid",
            branch=self.panel_br,
            designation="Executive",
            department="Sales",
        )
        self.walk_in = User.objects.create_user(
            mobile="+917521366888",
            password="x",
            name="Walk In Customer",
            role="user",
        )
        self.walk_in.is_active = False
        self.walk_in.save(update_fields=["is_active"])

        self.client = APIClient()
        self.client.force_authenticate(user=self.staff_admin)

    def test_lookup_unassigned_inactive_member_by_matri_id(self):
        res = self.client.get(
            "/api/v1/staff/payments/customer-lookup/",
            {"matri_id": self.walk_in.matri_id},
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data.get("success"))
        self.assertEqual(res.data["data"]["matri_id"], self.walk_in.matri_id)
        self.assertEqual(res.data["data"]["name"], "Walk In Customer")

    def test_lookup_unassigned_member_by_mobile(self):
        res = self.client.get(
            "/api/v1/staff/payments/customer-lookup/",
            {"mobile": "+917521366888"},
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["data"]["matri_id"], self.walk_in.matri_id)