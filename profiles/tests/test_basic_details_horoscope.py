"""PATCH /profile/basic/ optionally upserts UserProfile + HoroscopeProfile."""
from datetime import date, time, timedelta

from django.utils import timezone
from rest_framework.test import APIClient
from django.test import TestCase

from accounts.models import User
from astrology.models import HoroscopeProfile
from profiles.models import UserProfile


class BasicDetailsHoroscopeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            mobile='9300000003', password='x', role='user'
        )
        self.user.name = 'Basic Horoscope Member'
        self.user.dob = date(1998, 11, 11)
        self.user.email = 'basic-horo@example.com'
        self.user.save(update_fields=['name', 'dob', 'email'])
        self.client.force_authenticate(user=self.user)

    def test_patch_without_horoscope_keys_does_not_change_birth_data(self):
        resp = self.client.patch(
            '/api/v1/profile/basic/',
            {'name': 'Renamed Member'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['data']['name'], 'Renamed Member')
        self.assertFalse(resp.data['data']['horoscope']['has_horoscope'])
        self.assertFalse(
            UserProfile.objects.filter(user=self.user, has_horoscope=True).exists()
        )

    def test_patch_with_time_place_coords_creates_bridge(self):
        resp = self.client.patch(
            '/api/v1/profile/basic/',
            {
                'name': self.user.name,
                'has_horoscope': True,
                'time_of_birth': '10:30',
                'place_of_birth': 'Kochi',
                'birth_latitude': 9.9312,
                'birth_longitude': 76.2673,
                'birth_timezone': 5.5,
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        horo = resp.data['data']['horoscope']
        self.assertTrue(horo['has_horoscope'])
        self.assertEqual(horo['birth_place'], 'Kochi')
        self.assertAlmostEqual(float(horo['birth_latitude']), 9.9312, places=3)
        self.assertAlmostEqual(float(horo['birth_longitude']), 76.2673, places=3)

        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.has_horoscope)
        self.assertEqual(profile.time_of_birth, time(10, 30))
        self.assertEqual(profile.place_of_birth, 'Kochi')

        hp = HoroscopeProfile.objects.get(user=self.user)
        self.assertAlmostEqual(float(hp.pr_lat), 9.9312, places=3)
        self.assertAlmostEqual(float(hp.pr_lon), 76.2673, places=3)
        self.assertEqual(float(hp.pr_tz), 5.5)
        self.assertFalse(hp.is_calculated)
        self.assertIsNone(hp.calculated_at)

    def test_second_patch_updates_fields_and_bumps_updated_at(self):
        first = self.client.patch(
            '/api/v1/profile/basic/',
            {
                'has_horoscope': True,
                'time_of_birth': '10:30',
                'place_of_birth': 'Kochi',
                'birth_latitude': 9.9312,
                'birth_longitude': 76.2673,
                'birth_timezone': 5.5,
            },
            format='json',
        )
        self.assertEqual(first.status_code, 200, first.content)
        hp = HoroscopeProfile.objects.get(user=self.user)
        HoroscopeProfile.objects.filter(pk=hp.pk).update(
            updated_at=timezone.now() - timedelta(minutes=10)
        )
        hp.refresh_from_db()
        previous_updated_at = hp.updated_at

        second = self.client.patch(
            '/api/v1/profile/basic/',
            {
                'has_horoscope': True,
                'time_of_birth': '06:15',
                'place_of_birth': 'Kozhikode',
                'birth_latitude': 11.2588,
                'birth_longitude': 75.7804,
                'birth_timezone': 5.5,
            },
            format='json',
        )
        self.assertEqual(second.status_code, 200, second.content)
        horo = second.data['data']['horoscope']
        self.assertEqual(horo['birth_place'], 'Kozhikode')

        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.time_of_birth, time(6, 15))
        self.assertEqual(profile.place_of_birth, 'Kozhikode')

        hp.refresh_from_db()
        self.assertAlmostEqual(float(hp.pr_lat), 11.2588, places=3)
        self.assertEqual(hp.pr_tob, time(6, 15))
        self.assertGreater(hp.updated_at, previous_updated_at)
        self.assertFalse(hp.is_calculated)

    def test_patch_has_horoscope_true_without_time_place_returns_400(self):
        resp = self.client.patch(
            '/api/v1/profile/basic/',
            {'has_horoscope': True, 'name': self.user.name},
            format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(
            UserProfile.objects.filter(user=self.user, has_horoscope=True).exists()
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, 'Basic Horoscope Member')
