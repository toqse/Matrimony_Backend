"""Extended profile list filters (height, registration, horoscope, porutham)."""
import uuid
from datetime import timedelta
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from admin_panel.profile_filters import apply_profile_list_filters
from admin_panel.profile_porutham_filters import (
    REFERENCE_NOT_FOUND_MSG,
    apply_porutham_match_filters,
)
from astrology.models import HoroscopeProfile
from master.models import Height, IncomeRange
from profiles.models import UserEducation, UserPersonal, UserProfile


def _rasi_chart(moon_sign: int, length: int = 11) -> str:
    chars = []
    for i in range(length):
        if i == 2:
            chars.append(chr(ord("A") + moon_sign - 1))
        else:
            chars.append("A")
    return "".join(chars)


def _rasi_chart_planet_in_house(
    planet_index_0based: int,
    house_from_lagna: int,
    lagna_sign: int = 1,
) -> str:
    """Build an 11-char pr_rasi with one planet in ``house_from_lagna`` from Lagnam."""
    target_sign = ((lagna_sign + house_from_lagna - 2) % 12) + 1
    chars = [chr(ord("A") + lagna_sign - 1)] * 11
    chars[planet_index_0based] = chr(ord("A") + target_sign - 1)
    return "".join(chars)


def _mobile() -> str:
    return f"+9199{uuid.uuid4().int % 10**8:08d}"


def _matri_id() -> str:
    return f"TST{uuid.uuid4().hex[:10].upper()}"


def _req(params: dict):
    return SimpleNamespace(query_params=params)


def _create_member(**kwargs) -> User:
    kwargs.setdefault("password", "x")
    kwargs.setdefault("role", "user")
    kwargs.setdefault("matri_id", _matri_id())
    return User.objects.create_user(**kwargs)


class ProfileFiltersExtendedTests(TestCase):
    def setUp(self):
        suffix = uuid.uuid4().hex[:6]
        self.short = Height.objects.create(value_cm=155, display_label=f"5'1\" {suffix}")
        self.tall = Height.objects.create(value_cm=180, display_label=f"5'11\" {suffix}")
        self.income_low = IncomeRange.objects.create(name=f"Below 3L {suffix}", min_value=0, max_value=300000)
        self.income_high = IncomeRange.objects.create(name=f"Above 10L {suffix}", min_value=1000000, max_value=None)

        reg_old = timezone.now() - timedelta(days=100)
        reg_new = timezone.now() - timedelta(days=5)

        self.user_short = _create_member(
            mobile=_mobile(),
            name="Short User",
            gender="F",
        )
        User.objects.filter(pk=self.user_short.pk).update(created_at=reg_old)
        self.user_short.refresh_from_db()

        self.user_tall = _create_member(
            mobile=_mobile(),
            name="Tall User",
            gender="M",
        )
        User.objects.filter(pk=self.user_tall.pk).update(created_at=reg_new)
        self.user_tall.refresh_from_db()

        UserPersonal.objects.update_or_create(user=self.user_short, defaults={"height": self.short})
        UserPersonal.objects.update_or_create(user=self.user_tall, defaults={"height": self.tall})
        UserEducation.objects.update_or_create(user=self.user_short, defaults={"annual_income": self.income_low})
        UserEducation.objects.update_or_create(user=self.user_tall, defaults={"annual_income": self.income_high})

        self.user_no_chart = _create_member(
            mobile=_mobile(),
            name="No Chart",
            gender="M",
        )
        UserProfile.objects.filter(user=self.user_no_chart).update(has_horoscope=False)

        self.user_with_chart = _create_member(
            mobile=_mobile(),
            name="With Chart",
            gender="F",
        )
        UserProfile.objects.filter(user=self.user_with_chart).update(has_horoscope=True)
        HoroscopeProfile.objects.update_or_create(
            user=self.user_with_chart,
            defaults={
                "pr_star": 5,
                "pr_pada": 1,
                "pr_rasi": _rasi_chart(3),
                "rasi_sign": "Midhunam",
            },
        )

        self.base_qs = User.objects.filter(
            pk__in=[
                self.user_short.pk,
                self.user_tall.pk,
                self.user_no_chart.pk,
                self.user_with_chart.pk,
            ],
        )

    def test_height_range_filter(self):
        qs = apply_profile_list_filters(self.base_qs, _req({"height_from_cm": "170"}))
        ids = set(qs.values_list("pk", flat=True))
        self.assertIn(self.user_tall.pk, ids)
        self.assertNotIn(self.user_short.pk, ids)

        qs = apply_profile_list_filters(self.base_qs, _req({"height_to_cm": "160"}))
        ids = set(qs.values_list("pk", flat=True))
        self.assertIn(self.user_short.pk, ids)
        self.assertNotIn(self.user_tall.pk, ids)

    def test_income_filter(self):
        qs = apply_profile_list_filters(
            self.base_qs,
            _req({"income_id": str(self.income_high.pk)}),
        )
        ids = set(qs.values_list("pk", flat=True))
        self.assertEqual(ids, {self.user_tall.pk})

    def test_registered_date_filter(self):
        cutoff = (timezone.now() - timedelta(days=30)).date().isoformat()
        qs = apply_profile_list_filters(self.base_qs, _req({"registered_from": cutoff}))
        ids = set(qs.values_list("pk", flat=True))
        self.assertIn(self.user_tall.pk, ids)
        self.assertNotIn(self.user_short.pk, ids)

        old_cutoff = (timezone.now() - timedelta(days=90)).date().isoformat()
        qs = apply_profile_list_filters(self.base_qs, _req({"registered_to": old_cutoff}))
        ids = set(qs.values_list("pk", flat=True))
        self.assertIn(self.user_short.pk, ids)
        self.assertNotIn(self.user_tall.pk, ids)

    def test_has_horoscope_true_excludes_without_chart(self):
        qs = apply_profile_list_filters(self.base_qs, _req({"has_horoscope": "true"}))
        ids = set(qs.values_list("pk", flat=True))
        self.assertIn(self.user_with_chart.pk, ids)
        self.assertNotIn(self.user_no_chart.pk, ids)

    def test_rasi_id_filter(self):
        qs = apply_profile_list_filters(self.base_qs, _req({"rasi_id": "3"}))
        ids = set(qs.values_list("pk", flat=True))
        self.assertEqual(ids, {self.user_with_chart.pk})


class PlanetHouseFilterTests(TestCase):
    def setUp(self):
        self.user_sani_7 = _create_member(
            mobile=_mobile(),
            name="Sani 7th",
            gender="M",
        )
        self.user_sani_8 = _create_member(
            mobile=_mobile(),
            name="Sani 8th",
            gender="M",
        )
        self.user_short_chart = _create_member(
            mobile=_mobile(),
            name="Short Chart",
            gender="F",
        )

        HoroscopeProfile.objects.update_or_create(
            user=self.user_sani_7,
            defaults={
                "pr_star": 5,
                "pr_pada": 1,
                "pr_rasi": _rasi_chart_planet_in_house(7, 7),
            },
        )
        HoroscopeProfile.objects.update_or_create(
            user=self.user_sani_8,
            defaults={
                "pr_star": 5,
                "pr_pada": 1,
                "pr_rasi": _rasi_chart_planet_in_house(7, 8),
            },
        )
        HoroscopeProfile.objects.update_or_create(
            user=self.user_short_chart,
            defaults={
                "pr_star": 5,
                "pr_pada": 1,
                "pr_rasi": _rasi_chart(3, length=5),
            },
        )

        self.base_qs = User.objects.filter(
            pk__in=[
                self.user_sani_7.pk,
                self.user_sani_8.pk,
                self.user_short_chart.pk,
            ],
        )

    def test_planet_house_filter_matches_expected_user(self):
        qs = apply_profile_list_filters(
            self.base_qs,
            _req({"planet": "sani", "planet_house": "7"}),
        )
        ids = set(qs.values_list("pk", flat=True))
        self.assertEqual(ids, {self.user_sani_7.pk})

    def test_planet_house_filter_excludes_other_houses(self):
        qs = apply_profile_list_filters(
            self.base_qs,
            _req({"planet": "sani", "planet_house": "8"}),
        )
        ids = set(qs.values_list("pk", flat=True))
        self.assertEqual(ids, {self.user_sani_8.pk})

    def test_partial_planet_or_house_does_not_filter(self):
        qs = apply_profile_list_filters(self.base_qs, _req({"planet": "sani"}))
        self.assertEqual(qs.count(), 3)

        qs = apply_profile_list_filters(self.base_qs, _req({"planet_house": "7"}))
        self.assertEqual(qs.count(), 3)

    def test_incomplete_chart_excluded(self):
        qs = apply_profile_list_filters(
            self.base_qs,
            _req({"planet": "sani", "planet_house": "7"}),
        )
        ids = set(qs.values_list("pk", flat=True))
        self.assertNotIn(self.user_short_chart.pk, ids)


class PoruthamProfileFilterTests(TestCase):
    def setUp(self):
        tag = uuid.uuid4().hex[:8].upper()
        self.bride = _create_member(
            mobile=_mobile(),
            name="Ref Bride",
            gender="F",
            matri_id=f"REF{tag}",
        )

        self.groom_match = _create_member(
            mobile=_mobile(),
            name="Groom Match",
            gender="M",
        )
        self.groom_other = _create_member(
            mobile=_mobile(),
            name="Groom Other",
            gender="M",
        )

        HoroscopeProfile.objects.update_or_create(
            user=self.bride,
            defaults={
                "pr_star": 5,
                "pr_pada": 4,
                "pr_rasi": _rasi_chart(3),
                "rasi_sign": "Midhunam",
            },
        )
        HoroscopeProfile.objects.update_or_create(
            user=self.groom_match,
            defaults={
                "pr_star": 7,
                "pr_pada": 1,
                "pr_rasi": _rasi_chart(3),
                "rasi_sign": "Midhunam",
            },
        )
        HoroscopeProfile.objects.update_or_create(
            user=self.groom_other,
            defaults={
                "pr_star": 1,
                "pr_pada": 1,
                "pr_rasi": _rasi_chart(1),
                "rasi_sign": "Medam",
            },
        )

        self.base_qs = User.objects.filter(pk__in=[self.groom_match.pk, self.groom_other.pk])

    def test_invalid_reference_matri_id_returns_error(self):
        qs, err = apply_porutham_match_filters(
            self.base_qs,
            _req({"match_matri_id": "DOESNOTEXIST"}),
        )
        self.assertIsNone(qs)
        self.assertEqual(err, REFERENCE_NOT_FOUND_MSG)

    def test_porutham_filter_with_reference_returns_subset(self):
        qs, err = apply_porutham_match_filters(
            self.base_qs,
            _req({"match_matri_id": self.bride.matri_id, "min_porutham_count": "0"}),
        )
        self.assertIsNone(err)
        ids = set(qs.values_list("pk", flat=True))
        self.assertIn(self.groom_match.pk, ids)
        self.assertIn(self.groom_other.pk, ids)

    def test_porutham_high_min_count_can_exclude_candidates(self):
        qs, err = apply_porutham_match_filters(
            self.base_qs,
            _req({"match_matri_id": self.bride.matri_id, "min_porutham_count": "10"}),
        )
        self.assertIsNone(err)
        self.assertEqual(qs.count(), 0)
