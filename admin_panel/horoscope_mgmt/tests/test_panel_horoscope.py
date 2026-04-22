from datetime import date, time
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase

from accounts.models import User
from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch as PanelBranch
from admin_panel.horoscope_mgmt.services import panel_porutham, scoped_member_users_queryset
from admin_panel.staff_mgmt.models import StaffProfile
from admin_panel.subscriptions.models import CustomerStaffAssignment
from master.models import Branch as MasterBranch
from profiles.models import UserProfile


class _Request(SimpleNamespace):
    pass


class HoroscopePanelScopingTests(TestCase):
    def setUp(self):
        self.master_br = MasterBranch.objects.create(name="Test Branch", code="HP_SC_01")
        self.panel_br = PanelBranch.objects.create(
            name="Test Branch Panel",
            code="HP_SC_01",
            city="City",
            phone="9999999999",
            email="hp_sc_01_branch@test.invalid",
        )

        self.member_in = User.objects.create_user(
            mobile="+919876543210",
            password="x",
            name="Member In",
            role="user",
        )
        self.member_in.is_active = True
        self.member_in.branch = self.master_br
        self.member_in.save()

        self.member_out = User.objects.create_user(
            mobile="+919876543211",
            password="x",
            name="Member Out",
            role="user",
        )
        self.member_out.is_active = True
        self.member_out.branch = self.master_br
        self.member_out.save()

        UserProfile.objects.get_or_create(user=self.member_in, defaults={})
        UserProfile.objects.get_or_create(user=self.member_out, defaults={})

        self.admin_panel_user = AdminUser.objects.create(
            mobile="9000000001",
            name="Staff Login",
            role=AdminUser.ROLE_STAFF,
            branch_id=self.master_br.pk,
        )
        self.staff_profile = StaffProfile.objects.create(
            admin_user=self.admin_panel_user,
            name="Staff Person",
            mobile="8000000001",
            email="staff_hp@test.invalid",
            branch=self.panel_br,
            designation="Executive",
            department="Sales",
        )
        CustomerStaffAssignment.objects.create(user=self.member_in, staff=self.staff_profile)

        self.admin_super = AdminUser.objects.create(
            mobile="9000000002",
            name="Super Admin",
            role=AdminUser.ROLE_ADMIN,
        )

    def test_staff_scope_only_assigned_customers(self):
        req = _Request(user=self.admin_panel_user)
        qs = scoped_member_users_queryset(req, mount="staff")
        self.assertIsNotNone(qs)
        self.assertTrue(qs.filter(pk=self.member_in.pk).exists())
        self.assertFalse(qs.filter(pk=self.member_out.pk).exists())

    def test_admin_scope_includes_all_active_members(self):
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        self.assertIsNotNone(qs)
        self.assertTrue(qs.filter(pk=self.member_in.pk).exists())
        self.assertTrue(qs.filter(pk=self.member_out.pk).exists())

    def test_panel_porutham_rejects_when_groom_out_of_scope(self):
        p_in = UserProfile.objects.get(user=self.member_in)
        p_out = UserProfile.objects.get(user=self.member_out)
        req = _Request(user=self.admin_panel_user)
        qs = scoped_member_users_queryset(req, mount="staff")
        result, msg = panel_porutham(qs, p_in.pk, p_out.pk)
        self.assertIsNone(result)
        self.assertIn("scope", (msg or "").lower())


class HoroscopePanelRegenerateTests(TestCase):
    def setUp(self):
        self.master_br = MasterBranch.objects.create(name="Reg Branch", code="HP_RG_01")
        self.admin_super = AdminUser.objects.create(
            mobile="9000000003",
            name="Admin",
            role=AdminUser.ROLE_ADMIN,
        )
        self.member = User.objects.create_user(
            mobile="+919876543300",
            password="x",
            name="Has Birth",
            role="user",
            dob=date(1995, 6, 15),
        )
        self.member.is_active = True
        self.member.branch = self.master_br
        self.member.save()
        up, _ = UserProfile.objects.get_or_create(user=self.member, defaults={})
        up.time_of_birth = time(10, 30, 0)
        up.place_of_birth = "Chennai, India"
        up.save()

    @mock.patch("admin_panel.horoscope_mgmt.services.create_or_update_horoscope")
    def test_regenerate_calls_chart_pipeline_when_birth_complete(self, mock_create):
        from astrology.models import Horoscope
        from admin_panel.horoscope_mgmt.services import regenerate_horoscope

        profile = UserProfile.objects.get(user=self.member)
        fake = Horoscope(profile=profile, rasi="Mesha", nakshatra="Ashwini")
        fake.pk = 1
        mock_create.return_value = fake

        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        self.assertIsNotNone(qs)
        data, err = regenerate_horoscope(qs, self.member.pk)
        self.assertIsNone(err)
        mock_create.assert_called_once()
        self.assertIn("horoscope", data)
        self.assertEqual(data["horoscope"]["rasi"], "Mesha")
