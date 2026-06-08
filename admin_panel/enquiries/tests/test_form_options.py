from django.test import TestCase
from rest_framework.test import APIClient

from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch as PanelBranch
from admin_panel.enquiries.models import Enquiry
from admin_panel.staff_mgmt.models import StaffProfile
from master.models import Branch as MasterBranch

OPTIONS_URL = "/api/v1/admin/enquiries/options/"
ENQUIRIES_URL = "/api/v1/admin/enquiries/"


def _panel_branch(name: str, code: str) -> PanelBranch:
    return PanelBranch.objects.create(
        name=name,
        code=code,
        city="City",
        phone="9999999999",
        email=f"{code}@test.invalid",
    )


def _staff_profile(
    *,
    admin_user: AdminUser,
    branch: PanelBranch,
    name: str,
    mobile: str,
) -> StaffProfile:
    return StaffProfile.objects.create(
        admin_user=admin_user,
        name=name,
        mobile=mobile,
        email=f"{mobile}@test.invalid",
        branch=branch,
        designation="Executive",
        department="Sales",
        basic_salary=10000,
        monthly_target=10,
    )


class EnquiryFormOptionsTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.master_a = MasterBranch.objects.create(name="Branch A", code="ENQ_A")
        self.master_b = MasterBranch.objects.create(name="Branch B", code="ENQ_B")
        self.panel_a = _panel_branch("Branch A Panel", "ENQ_A")
        self.panel_b = _panel_branch("Branch B Panel", "ENQ_B")

        self.admin = AdminUser.objects.create(
            mobile="+919900000001",
            role=AdminUser.ROLE_ADMIN,
            name="Enquiry Admin",
            is_active=True,
        )

        self.staff_user_a = AdminUser.objects.create(
            mobile="+919900000101",
            role=AdminUser.ROLE_STAFF,
            name="Staff A",
            branch=self.master_a,
            is_active=True,
        )
        self.staff_profile_a = _staff_profile(
            admin_user=self.staff_user_a,
            branch=self.panel_a,
            name="Staff A",
            mobile="9000000101",
        )

        self.staff_user_b = AdminUser.objects.create(
            mobile="+919900000102",
            role=AdminUser.ROLE_STAFF,
            name="Staff B",
            branch=self.master_b,
            is_active=True,
        )
        _staff_profile(
            admin_user=self.staff_user_b,
            branch=self.panel_b,
            name="Staff B",
            mobile="9000000102",
        )

        self.manager = AdminUser.objects.create(
            mobile="+919900000201",
            role=AdminUser.ROLE_BRANCH_MANAGER,
            name="Branch Manager A",
            branch=self.master_a,
            is_active=True,
        )

    def test_admin_options_returns_branches_and_admin_user_staff_ids(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(OPTIONS_URL)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        branch_ids = {b["id"] for b in data["branches"]}
        self.assertIn(self.panel_a.pk, branch_ids)
        self.assertIn(self.panel_b.pk, branch_ids)

        staff_by_id = {s["id"]: s for s in data["staff"]}
        self.assertIn(self.staff_user_a.pk, staff_by_id)
        self.assertIn(self.staff_user_b.pk, staff_by_id)
        self.assertEqual(staff_by_id[self.staff_user_a.pk]["branch_id"], self.panel_a.pk)
        self.assertNotEqual(
            staff_by_id[self.staff_user_a.pk]["id"],
            self.staff_profile_a.pk,
        )

    def test_admin_options_filters_staff_by_branch_id(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(OPTIONS_URL, {"branch_id": self.panel_a.pk})
        self.assertEqual(resp.status_code, 200)
        staff_ids = {s["id"] for s in resp.json()["data"]["staff"]}
        self.assertEqual(staff_ids, {self.staff_user_a.pk})

    def test_branch_manager_sees_only_own_branch(self):
        self.client.force_authenticate(user=self.manager)
        resp = self.client.get(OPTIONS_URL)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data["branches"]), 1)
        self.assertEqual(data["branches"][0]["id"], self.panel_a.pk)
        staff_ids = {s["id"] for s in data["staff"]}
        self.assertEqual(staff_ids, {self.staff_user_a.pk})

    def test_create_enquiry_using_options_ids(self):
        self.client.force_authenticate(user=self.admin)
        payload = {
            "name": "Test Lead",
            "phone": "9876543210",
            "email": "lead@test.invalid",
            "source": "website",
            "branch": self.panel_a.pk,
            "assigned_to": self.staff_user_a.pk,
        }
        resp = self.client.post(ENQUIRIES_URL, payload, format="json")
        self.assertEqual(resp.status_code, 201)
        body = resp.json()["data"]
        self.assertEqual(body["name"], "Test Lead")
        self.assertEqual(body["branch"], self.panel_a.pk)
        self.assertEqual(body["branch_name"], self.panel_a.name)
        self.assertEqual(body["assigned_to"], self.staff_user_a.pk)
        self.assertEqual(body["assigned_to_name"], "Staff A")

        enquiry = Enquiry.objects.get(pk=body["id"])
        self.assertEqual(enquiry.branch_id, self.panel_a.pk)
        self.assertEqual(enquiry.assigned_to_id, self.staff_user_a.pk)
