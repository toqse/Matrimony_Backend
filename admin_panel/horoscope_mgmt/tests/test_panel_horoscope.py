from datetime import date
from types import SimpleNamespace

from django.test import RequestFactory, TestCase

from accounts.models import User
from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch as PanelBranch
from admin_panel.horoscope_mgmt.services import panel_porutham, scoped_member_users_queryset
from admin_panel.staff_mgmt.models import StaffProfile
from admin_panel.subscriptions.models import CustomerStaffAssignment
from astrology.models import HoroscopeProfile
from master.models import Branch as MasterBranch
from profiles.models import UserProfile


class _Request(SimpleNamespace):
    pass


def _rasi_string(moon_sign: int) -> str:
    """11-char A-L chart string; position index 2 = Moon rasi (1-12)."""
    chars = []
    for i in range(11):
        if i == 2:
            ch = chr(ord('A') + moon_sign - 1)
        else:
            ch = 'A'
        chars.append(ch)
    return ''.join(chars)


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


class HoroscopePanelPoruthamPayloadTests(TestCase):
    """panel_porutham attaches HoroscopeProfileSerializer data and VB porutham totals."""

    def setUp(self):
        self.master_br = MasterBranch.objects.create(name="Por Branch", code="HP_PR_01")
        self.admin_super = AdminUser.objects.create(
            mobile="9000000099",
            name="Admin Por",
            role=AdminUser.ROLE_ADMIN,
        )

        def _member(name: str, mobile: str, dob: date):
            u = User.objects.create_user(mobile=mobile, password="x", name=name, role="user", dob=dob)
            u.is_active = True
            u.branch = self.master_br
            u.save()
            return u

        self.bride_user = _member("Bride Test", "+919876543401", date(1996, 3, 10))
        self.groom_user = _member("Groom Test", "+919876543402", date(1994, 7, 22))
        self.bride_profile, _ = UserProfile.objects.get_or_create(user=self.bride_user, defaults={})
        self.groom_profile, _ = UserProfile.objects.get_or_create(user=self.groom_user, defaults={})

        HoroscopeProfile.objects.update_or_create(
            user=self.bride_user,
            defaults={
                'pr_rasi': _rasi_string(1),
                'pr_star': 1,
                'pr_pada': 1,
                'pr_name': 'Bride Test',
            },
        )
        HoroscopeProfile.objects.update_or_create(
            user=self.groom_user,
            defaults={
                'pr_rasi': _rasi_string(4),
                'pr_star': 5,
                'pr_pada': 2,
                'pr_name': 'Groom Test',
            },
        )

    def test_panel_porutham_includes_bride_groom_horoscope_and_scores(self):
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        self.assertIsNotNone(qs)
        http_request = RequestFactory().post("/api/v1/admin/horoscope/porutham/")
        result, msg = panel_porutham(
            qs,
            self.bride_profile.pk,
            self.groom_profile.pk,
            request=http_request,
        )
        self.assertIsNone(msg)
        self.assertIsNotNone(result)
        self.assertIn("bride_horoscope", result)
        self.assertIn("groom_horoscope", result)
        self.assertEqual(result["bride_horoscope"]["pr_star"], 1)
        self.assertEqual(result["groom_horoscope"]["pr_star"], 5)
        self.assertIn("poruthams", result)
        self.assertIn("score", result)
        self.assertIn("overall_result", result)
