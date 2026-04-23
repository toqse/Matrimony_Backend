from datetime import date, time
from types import SimpleNamespace
from unittest import mock

from django.test import RequestFactory, TestCase

from accounts.models import User
from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch as PanelBranch
from admin_panel.horoscope_mgmt.services import panel_porutham, scoped_member_users_queryset
from admin_panel.staff_mgmt.models import StaffProfile
from admin_panel.subscriptions.models import CustomerStaffAssignment
from astrology.models import Horoscope
from astrology.services.utils import build_birth_input_hash
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


class HoroscopePanelPoruthamPayloadTests(TestCase):
    """panel_porutham must attach full HoroscopeSerializer payloads (incl. grahanila) for admin clients."""

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

        dob_b, tob_b, pob_b = date(1996, 3, 10), time(8, 15, 0), "Kochi, India"
        dob_g, tob_g, pob_g = date(1994, 7, 22), time(9, 0, 0), "Trivandrum, India"
        grahanila_b = {"planets": {"moon": {"longitude": 10.0}}}
        grahanila_g = {"planets": {"moon": {"longitude": 100.0}}}

        Horoscope.objects.create(
            profile=self.bride_profile,
            date_of_birth=dob_b,
            time_of_birth=tob_b,
            place_of_birth=pob_b,
            latitude=9.93,
            longitude=76.27,
            lagna="Mesha",
            rasi="Mesha",
            nakshatra="Ashwini",
            nakshatra_pada=1,
            gana="Deva",
            yoni="Horse",
            nadi="Adi",
            rajju="Pada",
            grahanila=grahanila_b,
            birth_input_hash=build_birth_input_hash(dob_b, tob_b, pob_b),
        )
        Horoscope.objects.create(
            profile=self.groom_profile,
            date_of_birth=dob_g,
            time_of_birth=tob_g,
            place_of_birth=pob_g,
            latitude=8.52,
            longitude=76.94,
            lagna="Kanya",
            rasi="Mithuna",
            nakshatra="Mrigashira",
            nakshatra_pada=2,
            gana="Deva",
            yoni="Serpent",
            nadi="Madhya",
            rajju="Kanta",
            grahanila=grahanila_g,
            birth_input_hash=build_birth_input_hash(dob_g, tob_g, pob_g),
        )

    def test_panel_porutham_includes_bride_groom_horoscope_and_grahanila(self):
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
        self.assertIn("grahanila", result["bride_horoscope"])
        self.assertIn("grahanila", result["groom_horoscope"])
        self.assertIn("planets", result["bride_horoscope"]["grahanila"])
        self.assertEqual(result["bride_horoscope"]["nakshatra"], "Ashwini")
        self.assertEqual(result["groom_horoscope"]["nakshatra"], "Mrigashira")
        self.assertIn("poruthams", result)
        self.assertIn("score", result)
        self.assertIn("bride_chart_url", result)
        self.assertIn("groom_chart_url", result)
        self.assertIn("sig=", result["bride_chart_url"])
        self.assertIn("/api/v1/astrology/horoscope/", result["bride_chart_url"])
        self.assertIn("style=south", result["groom_chart_url"])


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
