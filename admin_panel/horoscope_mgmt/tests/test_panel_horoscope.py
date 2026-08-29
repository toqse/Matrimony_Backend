from datetime import date
from types import SimpleNamespace

from django.test import RequestFactory, TestCase

from accounts.models import User
from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch as PanelBranch
from admin_panel.horoscope_mgmt.services import (
    build_summary_counts,
    delete_saved_porutham_matches,
    list_horoscope_records,
    list_saved_porutham_matches,
    panel_porutham,
    save_porutham_matches,
    scoped_member_users_queryset,
)
from admin_panel.staff_mgmt.models import StaffProfile
from admin_panel.subscriptions.models import CustomerStaffAssignment
from astrology.models import AdminSavedPoruthamMatch, HoroscopeProfile, PoruthamResult
from master.models import Branch as MasterBranch
from profiles.models import UserProfile


class _Request(SimpleNamespace):
    pass


def _list_req(params: dict | None = None):
    return SimpleNamespace(query_params=params or {})


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

    def test_staff_scope_includes_all_active_members(self):
        req = _Request(user=self.admin_panel_user)
        qs = scoped_member_users_queryset(req, mount="staff")
        self.assertIsNotNone(qs)
        self.assertTrue(qs.filter(pk=self.member_in.pk).exists())
        self.assertTrue(qs.filter(pk=self.member_out.pk).exists())

    def test_admin_scope_includes_all_active_members(self):
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        self.assertIsNotNone(qs)
        self.assertTrue(qs.filter(pk=self.member_in.pk).exists())
        self.assertTrue(qs.filter(pk=self.member_out.pk).exists())

    def test_staff_scope_includes_both_profiles_for_porutham(self):
        p_in = UserProfile.objects.get(user=self.member_in)
        p_out = UserProfile.objects.get(user=self.member_out)
        req = _Request(user=self.admin_panel_user)
        qs = scoped_member_users_queryset(req, mount="staff")
        self.assertTrue(qs.filter(pk=self.member_in.pk).exists())
        self.assertTrue(qs.filter(pk=self.member_out.pk).exists())
        HoroscopeProfile.objects.update_or_create(
            user=self.member_in,
            defaults={
                "pr_rasi": _rasi_string(1),
                "pr_star": 1,
                "pr_pada": 1,
                "pr_name": "Member In",
            },
        )
        HoroscopeProfile.objects.update_or_create(
            user=self.member_out,
            defaults={
                "pr_rasi": _rasi_string(4),
                "pr_star": 5,
                "pr_pada": 2,
                "pr_name": "Member Out",
            },
        )
        result, msg = panel_porutham(qs, p_in.pk, p_out.pk)
        self.assertIsNone(msg)
        self.assertIsNotNone(result)


class HoroscopePanelSummaryCountTests(TestCase):
    def setUp(self):
        self.master_br = MasterBranch.objects.create(name="Sum Branch", code="HP_SM_01")
        self.other_br = MasterBranch.objects.create(name="Other Branch", code="HP_SM_02")
        self.admin_super = AdminUser.objects.create(
            mobile="9000000077",
            name="Admin Summary",
            role=AdminUser.ROLE_ADMIN,
        )
        self.manager = AdminUser.objects.create(
            mobile="9000000078",
            name="Branch Manager",
            role=AdminUser.ROLE_BRANCH_MANAGER,
            branch_id=self.master_br.pk,
        )

        def _member(name: str, mobile: str, branch: MasterBranch):
            u = User.objects.create_user(mobile=mobile, password="x", name=name, role="user")
            u.is_active = True
            u.branch = branch
            u.save()
            UserProfile.objects.get_or_create(user=u, defaults={})
            return u

        self.ready = _member("Ready Chart", "+919876543601", self.master_br)
        self.pending = _member("Pending Chart", "+919876543602", self.master_br)
        self.other = _member("Other Branch Member", "+919876543603", self.other_br)

        HoroscopeProfile.objects.update_or_create(
            user=self.ready,
            defaults={
                "pr_rasi": _rasi_string(1),
                "pr_star": 1,
                "pr_pada": 1,
                "pr_name": "Ready Chart",
                "is_calculated": False,
            },
        )
        HoroscopeProfile.objects.update_or_create(
            user=self.pending,
            defaults={
                "pr_rasi": "",
                "pr_star": None,
                "pr_name": "Pending Chart",
                "is_calculated": True,
            },
        )

    def test_generated_uses_ready_chart_not_is_calculated(self):
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        scoped = qs.filter(pk__in=[self.ready.pk, self.pending.pk, self.other.pk])
        data = build_summary_counts(scoped)
        self.assertEqual(data["total_horoscopes"], 3)
        self.assertEqual(data["jathagam_generated"], 1)
        self.assertEqual(data["pending_generation"], 2)
        self.assertNotIn("mangal_dosham", data)

    def test_branch_manager_scope_excludes_other_branches(self):
        req = _Request(user=self.manager)
        qs = scoped_member_users_queryset(req, mount="branch")
        self.assertIsNotNone(qs)
        ids = set(qs.values_list("pk", flat=True))
        self.assertIn(self.ready.pk, ids)
        self.assertIn(self.pending.pk, ids)
        self.assertNotIn(self.other.pk, ids)
        data = build_summary_counts(qs.filter(pk__in=[self.ready.pk, self.pending.pk, self.other.pk]))
        self.assertEqual(data["total_horoscopes"], 2)
        self.assertEqual(data["jathagam_generated"], 1)
        self.assertEqual(data["pending_generation"], 1)


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


class HoroscopePanelExeDoneFilterTests(TestCase):
    """list_horoscope_records exe_done filter matches panel_porutham eligibility."""

    def setUp(self):
        self.master_br = MasterBranch.objects.create(name="Exe Filter Branch", code="HP_EX_01")
        self.admin_super = AdminUser.objects.create(
            mobile="9000000088",
            name="Admin Exe Filter",
            role=AdminUser.ROLE_ADMIN,
        )

        def _female(name: str, mobile: str):
            u = User.objects.create_user(
                mobile=mobile,
                password="x",
                name=name,
                role="user",
                gender="F",
            )
            u.is_active = True
            u.branch = self.master_br
            u.save()
            UserProfile.objects.get_or_create(user=u, defaults={})
            return u

        self.eligible_user = _female("Exe Done Bride", "+919876543501")
        self.awaiting_user = _female("Awaiting Exe Bride", "+919876543502")

        HoroscopeProfile.objects.update_or_create(
            user=self.eligible_user,
            defaults={
                "pr_rasi": _rasi_string(2),
                "pr_star": 3,
                "pr_pada": 1,
                "pr_name": "Exe Done Bride",
            },
        )
        HoroscopeProfile.objects.update_or_create(
            user=self.awaiting_user,
            defaults={
                "pr_rasi": "",
                "pr_star": None,
                "pr_name": "Awaiting Exe Bride",
            },
        )

    def test_list_without_exe_done_includes_all_members(self):
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        list_req = _list_req({"gender": "F"})
        data, err = list_horoscope_records(
            qs, request=list_req, page=1, page_size=50,
        )
        self.assertIsNone(err)
        profile_ids = {row["profile_id"] for row in data["results"]}
        self.assertIn(UserProfile.objects.get(user=self.eligible_user).pk, profile_ids)
        self.assertIn(UserProfile.objects.get(user=self.awaiting_user).pk, profile_ids)

    def test_list_with_exe_done_returns_only_eligible_profiles(self):
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        list_req = _list_req({"gender": "F", "exe_done": "true"})
        data, err = list_horoscope_records(
            qs,
            request=list_req,
            page=1,
            page_size=50,
        )
        self.assertIsNone(err)
        profile_ids = {row["profile_id"] for row in data["results"]}
        self.assertIn(UserProfile.objects.get(user=self.eligible_user).pk, profile_ids)
        self.assertNotIn(UserProfile.objects.get(user=self.awaiting_user).pk, profile_ids)


class HoroscopePanelStarRasiRajjuFilterTests(TestCase):
    """Porutham picker list (exe_done) must honour star / rasi / rajju query params."""

    def setUp(self):
        self.master_br = MasterBranch.objects.create(name="Picker Filter Branch", code="HP_PF_01")
        self.admin_super = AdminUser.objects.create(
            mobile="9000000091",
            name="Admin Picker Filter",
            role=AdminUser.ROLE_ADMIN,
        )

        def _male(name: str, mobile: str):
            u = User.objects.create_user(
                mobile=mobile,
                password="x",
                name=name,
                role="user",
                gender="M",
            )
            u.is_active = True
            u.branch = self.master_br
            u.save()
            UserProfile.objects.get_or_create(user=u, defaults={})
            return u

        self.kanni_udara = _male("Kanni Udara", "+919876543601")
        self.midhunam_kanda = _male("Midhunam Kanda", "+919876543602")

        HoroscopeProfile.objects.update_or_create(
            user=self.kanni_udara,
            defaults={
                "pr_rasi": _rasi_string(6),
                "pr_star": 14,
                "pr_pada": 1,
                "rasi_sign": "",
                "rajju": "",
            },
        )
        HoroscopeProfile.objects.update_or_create(
            user=self.midhunam_kanda,
            defaults={
                "pr_rasi": _rasi_string(3),
                "pr_star": 8,
                "pr_pada": 1,
                "rasi_sign": "",
                "rajju": "",
            },
        )

    def _ids(self, params: dict) -> set:
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        list_req = _list_req({"gender": "M", "exe_done": "true", **params})
        data, err = list_horoscope_records(qs, request=list_req, page=1, page_size=50)
        self.assertIsNone(err)
        return {row["profile_id"] for row in data["results"]}

    def test_rasi_id_filters_exe_done_picker_list(self):
        kanni_id = UserProfile.objects.get(user=self.kanni_udara).pk
        other_id = UserProfile.objects.get(user=self.midhunam_kanda).pk
        ids = self._ids({"rasi_id": "6"})
        self.assertEqual(ids, {kanni_id})
        self.assertNotIn(other_id, ids)

    def test_pr_star_filters_exe_done_picker_list(self):
        kanda_id = UserProfile.objects.get(user=self.midhunam_kanda).pk
        ids = self._ids({"pr_star": "8"})
        self.assertEqual(ids, {kanda_id})

    def test_rajju_filters_exe_done_picker_list_from_star(self):
        kanda_id = UserProfile.objects.get(user=self.midhunam_kanda).pk
        ids = self._ids({"rajju": "Kanda"})
        self.assertEqual(ids, {kanda_id})


class HoroscopePanelSavedPoruthamTests(TestCase):
    def setUp(self):
        self.master_br = MasterBranch.objects.create(name="Saved Branch", code="HP_SV_01")
        self.admin_super = AdminUser.objects.create(
            mobile="9000000088",
            name="Admin Saved",
            role=AdminUser.ROLE_ADMIN,
        )

        def _member(name: str, mobile: str, gender: str):
            u = User.objects.create_user(mobile=mobile, password="x", name=name, role="user")
            u.is_active = True
            u.branch = self.master_br
            u.gender = gender
            u.save()
            return u

        self.bride_user = _member("Saved Bride", "+919876543601", "F")
        self.groom_user = _member("Saved Groom", "+919876543602", "M")
        self.bride_profile, _ = UserProfile.objects.get_or_create(user=self.bride_user, defaults={})
        self.groom_profile, _ = UserProfile.objects.get_or_create(user=self.groom_user, defaults={})

        HoroscopeProfile.objects.update_or_create(
            user=self.bride_user,
            defaults={
                "pr_rasi": _rasi_string(1),
                "pr_star": 1,
                "pr_pada": 1,
                "pr_name": "Saved Bride",
            },
        )
        HoroscopeProfile.objects.update_or_create(
            user=self.groom_user,
            defaults={
                "pr_rasi": _rasi_string(4),
                "pr_star": 5,
                "pr_pada": 2,
                "pr_name": "Saved Groom",
            },
        )

    def test_save_list_delete_shared_match_and_upsert_porutham_result(self):
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        self.assertIsNotNone(qs)

        saved, err = save_porutham_matches(
            qs,
            mode="fixed-bride",
            fixed_profile_id=self.bride_profile.pk,
            partner_profile_ids=[self.groom_profile.pk],
            saved_by=self.admin_super,
        )
        self.assertIsNone(err)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["partner_profile_id"], self.groom_profile.pk)
        self.assertTrue(saved[0]["overall_result"])

        self.assertEqual(
            AdminSavedPoruthamMatch.objects.filter(
                fixed_user=self.bride_user,
                partner_user=self.groom_user,
            ).count(),
            1,
        )
        self.assertTrue(
            PoruthamResult.objects.filter(
                bride=self.bride_user,
                groom=self.groom_user,
            ).exists()
        )

        rows, list_err = list_saved_porutham_matches(qs, self.bride_profile.pk)
        self.assertIsNone(list_err)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["partner_profile_id"], self.groom_profile.pk)

        deleted, del_err = delete_saved_porutham_matches(
            qs,
            fixed_profile_id=self.bride_profile.pk,
            partner_profile_ids=[self.groom_profile.pk],
        )
        self.assertIsNone(del_err)
        self.assertEqual(deleted, 1)
        self.assertFalse(
            AdminSavedPoruthamMatch.objects.filter(
                fixed_user=self.bride_user,
                partner_user=self.groom_user,
            ).exists()
        )
        self.assertTrue(
            PoruthamResult.objects.filter(
                bride=self.bride_user,
                groom=self.groom_user,
            ).exists()
        )

    def test_save_is_idempotent_for_same_pair(self):
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        self.assertIsNotNone(qs)

        save_porutham_matches(
            qs,
            mode="fixed-bride",
            fixed_profile_id=self.bride_profile.pk,
            partner_profile_ids=[self.groom_profile.pk],
            saved_by=self.admin_super,
        )
        save_porutham_matches(
            qs,
            mode="fixed-bride",
            fixed_profile_id=self.bride_profile.pk,
            partner_profile_ids=[self.groom_profile.pk],
            saved_by=self.admin_super,
        )
        self.assertEqual(AdminSavedPoruthamMatch.objects.count(), 1)
