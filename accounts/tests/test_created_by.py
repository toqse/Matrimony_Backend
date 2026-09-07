from unittest import mock

from django.test import TestCase, override_settings

from accounts.models import User
from accounts.serializers import VerifyOTPSerializer


LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "created-by-tests",
    }
}


class CreatedByLabelTests(TestCase):
    def test_website_default(self):
        user = User.objects.create_user(
            mobile="+919800000001",
            password="x",
            name="Web Member",
            role="user",
        )
        self.assertEqual(user.created_source, User.CREATED_SOURCE_WEBSITE)
        self.assertEqual(user.created_by_label(), "Website")

    def test_admin_and_bulk_labels(self):
        admin_user = User.objects.create_user(
            mobile="+919800000002",
            password="x",
            name="Admin Created",
            role="user",
            created_source=User.CREATED_SOURCE_ADMIN,
        )
        self.assertEqual(admin_user.created_by_label(), "Admin")

        bulk_user = User.objects.create_user(
            mobile="+919800000003",
            password="x",
            name="Bulk Member",
            role="user",
            created_source=User.CREATED_SOURCE_BULK,
        )
        self.assertEqual(bulk_user.created_by_label(), "Bulk upload")

    def test_staff_fallback_when_staff_deleted(self):
        from admin_panel.auth.models import AdminUser
        from admin_panel.branches.models import Branch as PanelBranch
        from admin_panel.staff_mgmt.models import StaffProfile
        from master.models import Branch as MasterBranch

        MasterBranch.objects.create(name="CB Branch", code="CB_LB_01")
        panel_br = PanelBranch.objects.create(
            name="CB Branch Panel",
            code="CB_LB_01",
            city="City",
            phone="9999990001",
            email="cb_lb_01@test.invalid",
        )
        admin = AdminUser.objects.create(
            mobile="9000000201",
            name="Label Staff Admin",
            role=AdminUser.ROLE_STAFF,
        )
        staff = StaffProfile.objects.create(
            admin_user=admin,
            name="Priya",
            mobile="8000000201",
            email="priya_cb@test.invalid",
            branch=panel_br,
            designation="Executive",
        )
        user = User.objects.create_user(
            mobile="+919800000004",
            password="x",
            name="Desk Member",
            role="user",
            created_source=User.CREATED_SOURCE_STAFF,
            created_by_staff=staff,
        )
        self.assertEqual(user.created_by_label(), "Priya")

        staff.delete()
        user.refresh_from_db()
        self.assertIsNone(user.created_by_staff_id)
        self.assertEqual(user.created_source, User.CREATED_SOURCE_STAFF)
        self.assertEqual(user.created_by_label(), "Staff")

    def test_branch_manager_fallback_without_staff(self):
        user = User.objects.create_user(
            mobile="+919800000005",
            password="x",
            name="BM Member",
            role="user",
            created_source=User.CREATED_SOURCE_BRANCH_MANAGER,
        )
        self.assertEqual(user.created_by_label(), "Branch Manager")


@override_settings(CACHES=LOCMEM_CACHES)
class WebsiteOtpCreatedByTests(TestCase):
    @mock.patch("accounts.services.verify_otp", return_value=(True, "ok"))
    @mock.patch(
        "accounts.services.pop_pending_registration",
        return_value={
            "name": "Website User",
            "dob": "1995-01-15",
            "gender": "F",
            "email": None,
            "profile_for": "myself",
        },
    )
    def test_verify_otp_sets_website_source(self, _pop, _verify):
        ser = VerifyOTPSerializer(
            data={"phone_number": "+919876543299", "otp": "123456"}
        )
        self.assertTrue(ser.is_valid(), ser.errors)
        user = ser.validated_data["user"]
        self.assertEqual(user.created_source, User.CREATED_SOURCE_WEBSITE)
        self.assertIsNone(user.created_by_staff_id)
        self.assertEqual(user.created_by_label(), "Website")
