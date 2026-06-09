"""POST/PATCH/GET /profile/location/ horoscope integration with the EXE bridge."""
from datetime import date

from rest_framework.test import APIClient
from django.test import TestCase

from accounts.models import User
from astrology.models import HoroscopeProfile
from profiles.models import UserProfile


class LocationHoroscopeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            mobile='9300000001', password='x', role='user'
        )
        self.user.name = 'Test Member'
        self.user.dob = date(1998, 11, 11)
        self.user.save(update_fields=['name', 'dob'])
        self.client.force_authenticate(user=self.user)

    def test_post_with_horoscope_creates_bridge_row(self):
        resp = self.client.post(
            '/api/v1/profile/location/',
            {
                'address': 'Kochi',
                'has_horoscope': True,
                'birth_time': '17:16',
                'birth_place': 'Kochi',
                'birth_latitude': 9.9312,
                'birth_longitude': 76.2673,
                'birth_timezone': 'Asia/Kolkata',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        hp = HoroscopeProfile.objects.get(user=self.user)
        self.assertAlmostEqual(float(hp.pr_lat), 9.9312, places=3)
        self.assertAlmostEqual(float(hp.pr_lon), 76.2673, places=3)
        self.assertEqual(float(hp.pr_tz), 5.5)
        self.assertFalse(hp.is_calculated)
        self.assertIsNone(hp.calculated_at)

        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.has_horoscope)
        self.assertEqual(profile.place_of_birth, 'Kochi')

    def test_post_has_horoscope_missing_required_returns_400(self):
        resp = self.client.post(
            '/api/v1/profile/location/',
            {'address': 'Kochi', 'has_horoscope': True},
            format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        # An empty bridge row is auto-created at registration; ensure no birth
        # coordinates were applied since validation failed.
        hp = HoroscopeProfile.objects.filter(user=self.user).first()
        if hp is not None:
            self.assertIsNone(hp.pr_lat)
            self.assertIsNone(hp.pr_lon)
        self.assertFalse(
            UserProfile.objects.filter(user=self.user, has_horoscope=True).exists()
        )

    def test_post_without_horoscope_is_legacy_noop(self):
        resp = self.client.post(
            '/api/v1/profile/location/',
            {'address': 'Kochi'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        # No horoscope keys -> helper is a no-op; the registration bridge row (if
        # any) stays without birth coordinates and the profile flag stays off.
        hp = HoroscopeProfile.objects.filter(user=self.user).first()
        if hp is not None:
            self.assertIsNone(hp.pr_lat)
            self.assertIsNone(hp.pr_lon)
        self.assertFalse(
            UserProfile.objects.filter(user=self.user, has_horoscope=True).exists()
        )

    def test_patch_applies_horoscope_and_get_returns_block(self):
        patch_resp = self.client.patch(
            '/api/v1/profile/location/',
            {
                'address': 'Kochi',
                'has_horoscope': True,
                'birth_time': '17:16',
                'birth_place': 'Kochi',
                'birth_latitude': 9.9312,
                'birth_longitude': 76.2673,
            },
            format='json',
        )
        self.assertEqual(patch_resp.status_code, 200, patch_resp.content)
        self.assertTrue(patch_resp.data['data']['horoscope']['has_horoscope'])

        get_resp = self.client.get('/api/v1/profile/location/')
        self.assertEqual(get_resp.status_code, 200, get_resp.content)
        block = get_resp.data['data']['horoscope']
        self.assertTrue(block['has_horoscope'])
        self.assertEqual(block['birth_place'], 'Kochi')
