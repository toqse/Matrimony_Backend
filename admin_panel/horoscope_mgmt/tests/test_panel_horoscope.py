from datetime import date
from types import SimpleNamespace

from django.test import RequestFactory, TestCase

from accounts.models import User
from admin_panel.auth.models import AdminUser
from admin_panel.branches.models import Branch as PanelBranch
from admin_panel.horoscope_mgmt.services import (
    build_summary_counts,
    delete_general_selections,
    delete_saved_porutham_matches,
    list_general_selection_groups,
    list_general_selections,
    list_horoscope_records,
    list_saved_porutham_groups,
    list_saved_porutham_matches,
    panel_porutham,
    save_general_selections,
    save_porutham_matches,
    scoped_member_users_queryset,
)
from admin_panel.staff_mgmt.models import StaffProfile
from admin_panel.subscriptions.models import CustomerStaffAssignment
from astrology.models import (
    AdminGeneralSelection,
    AdminSavedPoruthamMatch,
    HoroscopeProfile,
    PoruthamResult,
)
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


class HoroscopePanelSearchNameMatriTests(TestCase):
    """Porutham picker search= matches name OR matri_id (exact / prefix)."""

    def setUp(self):
        self.master_br = MasterBranch.objects.create(name="Search Branch", code="HP_SR_01")
        self.admin_super = AdminUser.objects.create(
            mobile="9000000095",
            name="Admin Search Filter",
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
            HoroscopeProfile.objects.update_or_create(
                user=u,
                defaults={
                    "pr_rasi": _rasi_string(4),
                    "pr_star": 5,
                    "pr_pada": 1,
                    "pr_name": name,
                },
            )
            return u

        self.target = _male("Gopikrishnan Search", "+919876543701")
        self.other = _male("Other Groom Search", "+919876543702")
        self.target_profile_id = UserProfile.objects.get(user=self.target).pk
        self.other_profile_id = UserProfile.objects.get(user=self.other).pk

    def _ids(self, params: dict) -> set:
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        list_req = _list_req({"gender": "M", "exe_done": "true", **params})
        data, err = list_horoscope_records(qs, request=list_req, page=1, page_size=50)
        self.assertIsNone(err)
        return {row["profile_id"] for row in data["results"]}

    def test_search_by_name_substring(self):
        ids = self._ids({"search": "Gopikrishnan"})
        self.assertIn(self.target_profile_id, ids)
        self.assertNotIn(self.other_profile_id, ids)

    def test_search_by_full_matri_id(self):
        mid = (self.target.matri_id or "").strip()
        self.assertTrue(mid)
        ids = self._ids({"search": mid})
        self.assertEqual(ids, {self.target_profile_id})

    def test_search_by_matri_id_prefix(self):
        mid = (self.target.matri_id or "").strip()
        self.assertTrue(len(mid) >= 4)
        prefix = mid[:4]
        ids = self._ids({"search": prefix})
        self.assertIn(self.target_profile_id, ids)

    def test_list_search_query_count_bounded(self):
        """select_related + single page materialization must stay O(1) vs page size."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        mid = (self.target.matri_id or "").strip()
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        list_req = _list_req({"gender": "M", "exe_done": "true", "search": mid})
        with CaptureQueriesContext(connection) as ctx:
            data, err = list_horoscope_records(qs, request=list_req, page=1, page_size=50)
        self.assertIsNone(err)
        self.assertEqual(len(data["results"]), 1)
        # Warm path typically ~few queries; hard-fail only if it looks like N+1.
        self.assertLessEqual(len(ctx.captured_queries), 30)


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
        self.assertEqual(rows[0]["fixed_profile_id"], self.bride_profile.pk)
        self.assertEqual(rows[0]["mode"], "fixed-bride")
        self.assertEqual(rows[0]["fixed_name"], "Saved Bride")
        self.assertEqual(rows[0]["partner_name"], "Saved Groom")

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

    def _second_pair(self):
        bride = User.objects.create_user(
            mobile="+919876543603", password="x", name="Other Bride", role="user"
        )
        bride.is_active = True
        bride.branch = self.master_br
        bride.gender = "F"
        bride.save()
        groom = User.objects.create_user(
            mobile="+919876543604", password="x", name="Other Groom", role="user"
        )
        groom.is_active = True
        groom.branch = self.master_br
        groom.gender = "M"
        groom.save()
        bride_profile, _ = UserProfile.objects.get_or_create(user=bride, defaults={})
        groom_profile, _ = UserProfile.objects.get_or_create(user=groom, defaults={})
        HoroscopeProfile.objects.update_or_create(
            user=bride,
            defaults={"pr_rasi": _rasi_string(2), "pr_star": 2, "pr_pada": 1, "pr_name": "Other Bride"},
        )
        HoroscopeProfile.objects.update_or_create(
            user=groom,
            defaults={"pr_rasi": _rasi_string(5), "pr_star": 6, "pr_pada": 2, "pr_name": "Other Groom"},
        )
        return bride_profile, groom_profile

    def test_list_all_saved_matches_without_fixed_profile(self):
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        other_bride, other_groom = self._second_pair()

        save_porutham_matches(
            qs,
            mode="fixed-bride",
            fixed_profile_id=self.bride_profile.pk,
            partner_profile_ids=[self.groom_profile.pk],
            saved_by=self.admin_super,
        )
        save_porutham_matches(
            qs,
            mode="fixed-groom",
            fixed_profile_id=other_groom.pk,
            partner_profile_ids=[other_bride.pk],
            saved_by=self.admin_super,
        )

        all_rows, err = list_saved_porutham_matches(qs)
        self.assertIsNone(err)
        self.assertEqual(len(all_rows), 2)
        modes = {row["mode"] for row in all_rows}
        self.assertEqual(modes, {"fixed-bride", "fixed-groom"})
        fixed_ids = {row["fixed_profile_id"] for row in all_rows}
        self.assertEqual(fixed_ids, {self.bride_profile.pk, other_groom.pk})

        filtered, ferr = list_saved_porutham_matches(qs, self.bride_profile.pk)
        self.assertIsNone(ferr)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["fixed_profile_id"], self.bride_profile.pk)

    def test_list_saved_matches_search_by_name_or_matri(self):
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        other_bride, other_groom = self._second_pair()

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
            fixed_profile_id=other_bride.pk,
            partner_profile_ids=[other_groom.pk],
            saved_by=self.admin_super,
        )

        by_name, err = list_saved_porutham_matches(qs, search="Saved Bride")
        self.assertIsNone(err)
        self.assertEqual(len(by_name), 1)
        self.assertEqual(by_name[0]["fixed_profile_id"], self.bride_profile.pk)

        by_matri, merr = list_saved_porutham_matches(qs, search=self.groom_user.matri_id)
        self.assertIsNone(merr)
        self.assertEqual(len(by_matri), 1)
        self.assertEqual(by_matri[0]["partner_profile_id"], self.groom_profile.pk)

    def _extra_groom(self, name: str, mobile: str, star: int, rasi: int):
        groom = User.objects.create_user(mobile=mobile, password="x", name=name, role="user")
        groom.is_active = True
        groom.branch = self.master_br
        groom.gender = "M"
        groom.save()
        profile, _ = UserProfile.objects.get_or_create(user=groom, defaults={})
        HoroscopeProfile.objects.update_or_create(
            user=groom,
            defaults={"pr_rasi": _rasi_string(rasi), "pr_star": star, "pr_pada": 1, "pr_name": name},
        )
        return profile

    def test_groups_one_fixed_profile_with_two_partners(self):
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        second_groom = self._extra_groom("Second Groom", "+919876543605", star=7, rasi=6)

        save_porutham_matches(
            qs,
            mode="fixed-bride",
            fixed_profile_id=self.bride_profile.pk,
            partner_profile_ids=[self.groom_profile.pk, second_groom.pk],
            saved_by=self.admin_super,
        )
        other_bride, other_groom = self._second_pair()
        save_porutham_matches(
            qs,
            mode="fixed-groom",
            fixed_profile_id=other_groom.pk,
            partner_profile_ids=[other_bride.pk],
            saved_by=self.admin_super,
        )

        data, err = list_saved_porutham_groups(qs, page=1, page_size=20)
        self.assertIsNone(err)
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["results"]), 2)
        by_fixed = {row["fixed_profile_id"]: row for row in data["results"]}
        self.assertEqual(by_fixed[self.bride_profile.pk]["match_count"], 2)
        self.assertEqual(by_fixed[self.bride_profile.pk]["mode"], "fixed-bride")
        self.assertEqual(by_fixed[self.bride_profile.pk]["fixed_name"], "Saved Bride")
        self.assertEqual(by_fixed[other_groom.pk]["match_count"], 1)

        paged, perr = list_saved_porutham_groups(qs, page=1, page_size=1)
        self.assertIsNone(perr)
        self.assertEqual(paged["count"], 2)
        self.assertEqual(len(paged["results"]), 1)
        self.assertEqual(paged["page"], 1)
        self.assertEqual(paged["page_size"], 1)

        by_partner, serr = list_saved_porutham_groups(qs, search="Second Groom")
        self.assertIsNone(serr)
        self.assertEqual(by_partner["count"], 1)
        self.assertEqual(by_partner["results"][0]["fixed_profile_id"], self.bride_profile.pk)

    def test_list_saved_matches_pagination(self):
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        second_groom = self._extra_groom("Paged Groom", "+919876543606", star=8, rasi=7)
        save_porutham_matches(
            qs,
            mode="fixed-bride",
            fixed_profile_id=self.bride_profile.pk,
            partner_profile_ids=[self.groom_profile.pk, second_groom.pk],
            saved_by=self.admin_super,
        )

        page1, err = list_saved_porutham_matches(
            qs, self.bride_profile.pk, page=1, page_size=1
        )
        self.assertIsNone(err)
        self.assertEqual(page1["count"], 2)
        self.assertEqual(len(page1["results"]), 1)
        self.assertEqual(page1["page"], 1)

        page2, err2 = list_saved_porutham_matches(
            qs, self.bride_profile.pk, page=2, page_size=1
        )
        self.assertIsNone(err2)
        self.assertEqual(len(page2["results"]), 1)
        self.assertNotEqual(
            page1["results"][0]["partner_profile_id"],
            page2["results"][0]["partner_profile_id"],
        )


class HoroscopePanelGeneralSelectionTests(TestCase):
    """General Selection shortlist: no horoscope required."""

    def setUp(self):
        self.master_br = MasterBranch.objects.create(name="Gen Sel Branch", code="HP_GS_01")
        self.admin_super = AdminUser.objects.create(
            mobile="9000000099",
            name="Admin Gen Sel",
            role=AdminUser.ROLE_ADMIN,
        )

        def _member(name: str, mobile: str, gender: str):
            u = User.objects.create_user(mobile=mobile, password="x", name=name, role="user")
            u.is_active = True
            u.branch = self.master_br
            u.gender = gender
            u.save()
            return u

        self.bride_user = _member("Gen Bride", "+919876543801", "F")
        self.groom_user = _member("Gen Groom", "+919876543802", "M")
        self.bride_no_hp = _member("No Chart Bride", "+919876543803", "F")
        self.groom_no_hp = _member("No Chart Groom", "+919876543804", "M")
        self.bride_profile, _ = UserProfile.objects.get_or_create(user=self.bride_user, defaults={})
        self.groom_profile, _ = UserProfile.objects.get_or_create(user=self.groom_user, defaults={})
        self.bride_no_hp_profile, _ = UserProfile.objects.get_or_create(
            user=self.bride_no_hp, defaults={}
        )
        self.groom_no_hp_profile, _ = UserProfile.objects.get_or_create(
            user=self.groom_no_hp, defaults={}
        )

    def test_save_general_selection_without_horoscope(self):
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        saved, err = save_general_selections(
            qs,
            mode="fixed-bride",
            fixed_profile_id=self.bride_no_hp_profile.pk,
            partner_profile_ids=[self.groom_no_hp_profile.pk],
            saved_by=self.admin_super,
        )
        self.assertIsNone(err)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["partner_profile_id"], self.groom_no_hp_profile.pk)
        self.assertEqual(
            AdminGeneralSelection.objects.filter(
                fixed_user=self.bride_no_hp,
                partner_user=self.groom_no_hp,
            ).count(),
            1,
        )
        self.assertFalse(
            PoruthamResult.objects.filter(
                bride=self.bride_no_hp,
                groom=self.groom_no_hp,
            ).exists()
        )

    def test_list_groups_and_delete(self):
        req = _Request(user=self.admin_super)
        qs = scoped_member_users_queryset(req, mount="admin")
        save_general_selections(
            qs,
            mode="fixed-bride",
            fixed_profile_id=self.bride_profile.pk,
            partner_profile_ids=[self.groom_profile.pk, self.groom_no_hp_profile.pk],
            saved_by=self.admin_super,
        )
        groups, gerr = list_general_selection_groups(qs, page=1, page_size=20)
        self.assertIsNone(gerr)
        self.assertGreaterEqual(groups["count"], 1)
        fixed_ids = {r["fixed_profile_id"] for r in groups["results"]}
        self.assertIn(self.bride_profile.pk, fixed_ids)

        rows, lerr = list_general_selections(qs, self.bride_profile.pk)
        self.assertIsNone(lerr)
        self.assertEqual(len(rows), 2)

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            list_general_selections(qs, self.bride_profile.pk)
        self.assertLessEqual(len(ctx.captured_queries), 12)

        deleted, derr = delete_general_selections(
            qs,
            fixed_profile_id=self.bride_profile.pk,
            partner_profile_ids=[self.groom_profile.pk],
        )
        self.assertIsNone(derr)
        self.assertEqual(deleted, 1)
        remaining, _ = list_general_selections(qs, self.bride_profile.pk)
        self.assertEqual(len(remaining), 1)
