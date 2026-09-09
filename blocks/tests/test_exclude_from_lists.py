"""Blocked peers must not appear in Interest or Matching list API responses."""
from datetime import date, timedelta

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from blocks.models import UserBlock
from matches.services import preferred_match_queryset
from plans.models import Interest
from profiles.models import UserProfile

LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "blocks-exclude-tests",
    }
}


def _years_ago(years):
    return date.today() - timedelta(days=365 * years)


def _visible_user(*, mobile, gender, dob=None, name=None):
    user = User.objects.create_user(
        mobile=mobile,
        password="x",
        role="user",
        gender=gender,
        dob=dob or _years_ago(30),
        name=name or mobile,
        is_active=True,
    )
    UserProfile.objects.create(
        user=user,
        location_completed=True,
        religion_completed=True,
        personal_completed=True,
        family_completed=True,
        education_completed=True,
        about_completed=True,
        photos_completed=True,
    )
    return user


@override_settings(CACHES=LOCMEM_CACHES, ALLOWED_HOSTS=["*", "testserver"])
class BlockExcludeInterestListTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.viewer = _visible_user(mobile="9120000001", gender="M", name="Viewer")
        self.sent_peer = _visible_user(mobile="9120000002", gender="F", name="SentPeer")
        self.received_peer = _visible_user(mobile="9120000003", gender="F", name="ReceivedPeer")
        self.other_sent = _visible_user(mobile="9120000004", gender="F", name="OtherSent")
        self.other_received = _visible_user(mobile="9120000005", gender="F", name="OtherReceived")

        Interest.objects.create(
            sender=self.viewer,
            receiver=self.sent_peer,
            status=Interest.STATUS_PENDING,
        )
        Interest.objects.create(
            sender=self.viewer,
            receiver=self.other_sent,
            status=Interest.STATUS_PENDING,
        )
        Interest.objects.create(
            sender=self.received_peer,
            receiver=self.viewer,
            status=Interest.STATUS_PENDING,
        )
        Interest.objects.create(
            sender=self.other_received,
            receiver=self.viewer,
            status=Interest.STATUS_PENDING,
        )

        UserBlock.objects.create(blocker=self.viewer, blocked=self.sent_peer)
        UserBlock.objects.create(blocker=self.viewer, blocked=self.received_peer)
        self.client.force_authenticate(user=self.viewer)

    def _matri_ids(self, results):
        return {item["matri_id"] for item in results}

    def test_my_interests_excludes_blocked_counterparties(self):
        res = self.client.get("/api/v1/interests/my/")
        self.assertEqual(res.status_code, 200)
        data = res.data["data"]
        self.assertNotIn(self.sent_peer.matri_id, self._matri_ids(data["sent"]["results"]))
        self.assertNotIn(self.received_peer.matri_id, self._matri_ids(data["received"]["results"]))
        self.assertIn(self.other_sent.matri_id, self._matri_ids(data["sent"]["results"]))
        self.assertIn(self.other_received.matri_id, self._matri_ids(data["received"]["results"]))
        self.assertEqual(data["sent"]["total"], 1)
        self.assertEqual(data["received"]["total"], 1)

    def test_sent_and_received_lists_exclude_blocked(self):
        sent = self.client.get("/api/v1/interests/sent/")
        received = self.client.get("/api/v1/interests/received/")
        self.assertEqual(sent.status_code, 200)
        self.assertEqual(received.status_code, 200)
        self.assertNotIn(self.sent_peer.matri_id, self._matri_ids(sent.data["data"]["results"]))
        self.assertIn(self.other_sent.matri_id, self._matri_ids(sent.data["data"]["results"]))
        self.assertNotIn(self.received_peer.matri_id, self._matri_ids(received.data["data"]["results"]))
        self.assertIn(self.other_received.matri_id, self._matri_ids(received.data["data"]["results"]))

    def test_dashboard_summary_interest_counts_exclude_blocked(self):
        res = self.client.get("/api/v1/dashboard/summary/")
        self.assertEqual(res.status_code, 200)
        data = res.data["data"]
        self.assertEqual(data["interests_sent"], 1)
        self.assertEqual(data["interests_received"], 1)


@override_settings(CACHES=LOCMEM_CACHES, ALLOWED_HOSTS=["*", "testserver"])
class BlockExcludeMatchingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.viewer = _visible_user(mobile="9130000001", gender="M", name="MatchViewer")
        self.blocked_peer = _visible_user(mobile="9130000002", gender="F", name="BlockedPeer")
        self.visible_peer = _visible_user(mobile="9130000003", gender="F", name="VisiblePeer")
        UserBlock.objects.create(blocker=self.viewer, blocked=self.blocked_peer)
        self.client.force_authenticate(user=self.viewer)

    def test_preferred_match_queryset_excludes_blocked(self):
        ids = set(preferred_match_queryset(self.viewer).values_list("pk", flat=True))
        self.assertNotIn(self.blocked_peer.pk, ids)
        self.assertIn(self.visible_peer.pk, ids)

    def test_matches_list_excludes_blocked(self):
        res = self.client.get("/api/v1/matches/", {"page": 1, "limit": 50})
        self.assertEqual(res.status_code, 200)
        matri_ids = {p["matri_id"] for p in res.data["data"]["profiles"]}
        self.assertNotIn(self.blocked_peer.matri_id, matri_ids)
        self.assertIn(self.visible_peer.matri_id, matri_ids)

    def test_dashboard_new_matches_excludes_blocked(self):
        res = self.client.get("/api/v1/dashboard/new-matches/?limit=20")
        self.assertEqual(res.status_code, 200)
        matri_ids = {p["matri_id"] for p in res.data["data"]}
        self.assertNotIn(self.blocked_peer.matri_id, matri_ids)
        self.assertIn(self.visible_peer.matri_id, matri_ids)

    def test_dashboard_summary_new_matches_excludes_blocked(self):
        res = self.client.get("/api/v1/dashboard/summary/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["data"]["new_matches"], 1)
