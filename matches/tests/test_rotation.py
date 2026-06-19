"""Tests for daily profile rotation (Phase 1)."""
from datetime import date

from django.test import TestCase, override_settings

from accounts.models import User
from matches.rotation import annotate_daily_rotation_rank, get_daily_rotation_seed


class DailyRotationSeedTests(TestCase):
    @override_settings(TIME_ZONE="Asia/Kolkata")
    def test_get_daily_rotation_seed_formats_yyyymmdd(self):
        self.assertEqual(get_daily_rotation_seed(for_date=date(2025, 6, 19)), "20250619")


class DailyRotationRankTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(
            mobile="9100000001", password="x", role="user", gender="F",
        )
        self.user_b = User.objects.create_user(
            mobile="9100000002", password="x", role="user", gender="F",
        )

    def _rank_for(self, user, seed):
        row = (
            annotate_daily_rotation_rank(User.objects.filter(pk=user.pk), seed=seed)
            .values("daily_rotation_rank")
            .first()
        )
        return row["daily_rotation_rank"]

    def test_same_pk_and_seed_produces_identical_rank(self):
        seed = "20250619"
        rank_first = self._rank_for(self.user_a, seed)
        rank_second = self._rank_for(self.user_a, seed)
        self.assertEqual(rank_first, rank_second)

    def test_different_seeds_produce_different_ranks(self):
        rank_day_one = self._rank_for(self.user_a, "20250619")
        rank_day_two = self._rank_for(self.user_a, "20250620")
        self.assertNotEqual(rank_day_one, rank_day_two)

    def test_ordering_is_stable_for_fixed_seed(self):
        seed = "20250619"
        qs = annotate_daily_rotation_rank(
            User.objects.filter(pk__in=[self.user_a.pk, self.user_b.pk]),
            seed=seed,
        ).order_by("daily_rotation_rank", "pk")
        first_run = list(qs.values_list("pk", flat=True))
        second_run = list(qs.values_list("pk", flat=True))
        self.assertEqual(first_run, second_run)

    def test_pagination_slices_are_disjoint_with_stable_order(self):
        seed = "20250619"
        users = [
            User.objects.create_user(
                mobile=f"91000000{i:02d}", password="x", role="user", gender="F",
            )
            for i in range(10, 15)
        ]
        qs = annotate_daily_rotation_rank(
            User.objects.filter(pk__in=[u.pk for u in users]),
            seed=seed,
        ).order_by("daily_rotation_rank", "pk")
        page_one = list(qs[:2].values_list("pk", flat=True))
        page_two = list(qs[2:4].values_list("pk", flat=True))
        self.assertEqual(len(page_one), 2)
        self.assertEqual(len(page_two), 2)
        self.assertFalse(set(page_one) & set(page_two))
