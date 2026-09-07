from django.test import RequestFactory, TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch as PanelBranch
from admin_panel.my_profiles.views import _build_list_row
from admin_panel.staff_mgmt.models import StaffProfile
from admin_panel.staff_profiles.registration import create_user_and_profile_sections
from admin_panel.staff_profiles.views import _build_staff_list_row
from admin_panel.subscriptions.models import CustomerStaffAssignment
from master.models import Branch as MasterBranch

LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "staff-created-by-tests",
    }
}


@override_settings(CACHES=LOCMEM_CACHES)
class ProfileCreatedByTests(TestCase):
    def setUp(self):
        self.master_br = MasterBranch.objects.create(name="CB Create Branch", code="CB_CR_01")
        self.panel_br = PanelBranch.objects.create(
            name="CB Create Branch Panel",
            code="CB_CR_01",
            city="City",
            phone="9999990101",
            email="cb_cr_01@test.invalid",
        )
        self.staff_admin = AdminUser.objects.create(
            mobile="9000000301",
            name="Create Staff",
            role=AdminUser.ROLE_STAFF,
            is_active=True,
        )
        self.staff = StaffProfile.objects.create(
            admin_user=self.staff_admin,
            name="Priya Kumar",
            mobile="8000000301",
            email="priya_create@test.invalid",
            branch=self.panel_br,
            designation="Executive",
        )
        self.admin = AdminUser.objects.create(
            mobile="9000000302",
            name="Create Admin",
            role=AdminUser.ROLE_ADMIN,
            is_active=True,
        )
        self.factory = RequestFactory()
        self.client = APIClient()

    def _create_kwargs(self, mobile, name="Member"):
        return {
            "name": name,
            "mobile": mobile,
            "gender": "F",
            "dob_iso": "1995-01-15",
            "email": None,
            "branch_pk": self.master_br.pk,
            "data": {},
            "files": {},
        }

    def test_staff_create_sets_staff_source_and_list_label(self):
        user = create_user_and_profile_sections(
            **self._create_kwargs("+919811100101", "Staff Created"),
            staff=self.staff,
            created_source=User.CREATED_SOURCE_STAFF,
            created_by_staff=self.staff,
        )
        user.refresh_from_db()
        self.assertEqual(user.created_source, User.CREATED_SOURCE_STAFF)
        self.assertEqual(user.created_by_staff_id, self.staff.pk)
        self.assertEqual(user.created_by_label(), "Priya Kumar")
        self.assertTrue(
            CustomerStaffAssignment.objects.filter(user=user, staff=self.staff).exists()
        )

        request = self.factory.get("/api/v1/staff/profiles/")
        row = _build_staff_list_row(request, user)
        self.assertEqual(row["created_by"], "Priya Kumar")

        branch_row = _build_list_row(request, user)
        self.assertEqual(branch_row["created_by"], "Priya Kumar")

    def test_admin_create_with_staff_id_keeps_admin_as_creator(self):
        user = create_user_and_profile_sections(
            **self._create_kwargs("+919811100102", "Admin Assigned"),
            staff=self.staff,
            created_source=User.CREATED_SOURCE_ADMIN,
            created_by_staff=None,
        )
        user.refresh_from_db()
        self.assertEqual(user.created_source, User.CREATED_SOURCE_ADMIN)
        self.assertIsNone(user.created_by_staff_id)
        self.assertEqual(user.created_by_label(), "Admin")
        self.assertTrue(
            CustomerStaffAssignment.objects.filter(user=user, staff=self.staff).exists()
        )

        request = self.factory.get("/api/v1/staff/profiles/")
        self.assertEqual(_build_staff_list_row(request, user)["created_by"], "Admin")

    def test_admin_create_api_does_not_treat_staff_id_as_creator(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/v1/admin/profiles/create/",
            {
                "name": "Admin API Member",
                "phone_number": "9811100103",
                "gender": "F",
                "dob": "15-01-1995",
                "terms_accepted": True,
                "staff_id": self.staff.pk,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        matri_id = res.data["data"]["matri_id"]
        user = User.objects.get(matri_id=matri_id)
        self.assertEqual(user.created_source, User.CREATED_SOURCE_ADMIN)
        self.assertIsNone(user.created_by_staff_id)
        self.assertEqual(user.created_by_label(), "Admin")
        self.assertTrue(
            CustomerStaffAssignment.objects.filter(user=user, staff=self.staff).exists()
        )

    def test_staff_list_api_returns_created_by(self):
        create_user_and_profile_sections(
            **self._create_kwargs("+919811100104", "Listed Staff Created"),
            staff=self.staff,
            created_source=User.CREATED_SOURCE_STAFF,
            created_by_staff=self.staff,
        )
        web = User.objects.create_user(
            mobile="+919811100105",
            password="x",
            name="Listed Website",
            role="user",
            created_source=User.CREATED_SOURCE_WEBSITE,
        )
        web.is_active = True
        web.save(update_fields=["is_active"])

        self.client.force_authenticate(user=self.staff_admin)
        res = self.client.get("/api/v1/staff/profiles/", {"page_size": 100})
        self.assertEqual(res.status_code, 200, res.data)
        rows = {r["name"]: r["created_by"] for r in res.data["data"]["results"]}
        self.assertEqual(rows.get("Listed Staff Created"), "Priya Kumar")
        self.assertEqual(rows.get("Listed Website"), "Website")
