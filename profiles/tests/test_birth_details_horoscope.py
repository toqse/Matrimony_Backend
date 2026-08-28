"""GET/POST/PATCH /profile/birth-details/ upserts UserProfile + HoroscopeProfile."""
from datetime import date, time

from rest_framework.test import APIClient
from django.test import TestCase

from accounts.models import User
from astrology.models import HoroscopeProfile
from profiles.models import UserProfile


class BirthDetailsHoroscopeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            mobile='9300000002', password='x', role='user'
        )
        self.user.name = 'Birth Details Member'
        self.user.dob = date(1998, 11, 11)
        self.user.save(update_fields=['name', 'dob'])
        self.client.force_authenticate(user=self.user)

    def test_get_empty_when_not_added(self):
        resp = self.client.get('/api/v1/profile/birth-details/')
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.data['data']
        self.assertFalse(data['has_horoscope'])
        self.assertIn(data.get('time_of_birth'), (None, ''))
        self.assertEqual(data.get('place_of_birth') or '', '')

    def test_post_adds_birth_details_and_bridge_row(self):
        resp = self.client.post(
            '/api/v1/profile/birth-details/',
            {
                'time_of_birth': '10:30',
                'place_of_birth': 'Kochi',
                'birth_latitude': 9.9312,
                'birth_longitude': 76.2673,
                'birth_timezone': 5.5,
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.data['data']
        self.assertTrue(data['has_horoscope'])
        self.assertEqual(data['time_of_birth'], '10:30')
        self.assertEqual(data['place_of_birth'], 'Kochi')
        self.assertAlmostEqual(float(data['birth_latitude']), 9.9312, places=3)
        self.assertAlmostEqual(float(data['birth_longitude']), 76.2673, places=3)

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

    def test_post_legacy_time_and_place_only_creates_bridge(self):
        resp = self.client.post(
            '/api/v1/profile/birth-details/',
            {
                'time_of_birth': '17:16:00',
                'place_of_birth': 'Thrissur',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.data['data']['has_horoscope'])
        self.assertEqual(resp.data['data']['place_of_birth'], 'Thrissur')
        self.assertTrue(
            HoroscopeProfile.objects.filter(user=self.user).exists()
        )
        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.has_horoscope)
        self.assertEqual(profile.time_of_birth, time(17, 16))

    def test_patch_updates_existing_and_resets_calculated(self):
        HoroscopeProfile.objects.update_or_create(
            user=self.user,
            defaults={
                'pr_name': self.user.name,
                'pr_dob': self.user.dob,
                'pr_tob': time(8, 0),
                'pr_lat': 9.0,
                'pr_lon': 76.0,
                'pr_tz': 5.5,
                'is_calculated': True,
            },
        )
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={
                'has_horoscope': True,
                'time_of_birth': time(8, 0),
                'place_of_birth': 'Kochi',
                'birth_latitude': 9.0,
                'birth_longitude': 76.0,
                'birth_timezone': 5.5,
            },
        )

        resp = self.client.patch(
            '/api/v1/profile/birth-details/',
            {
                'time_of_birth': '06:15',
                'place_of_birth': 'Kozhikode',
                'birth_latitude': 11.2588,
                'birth_longitude': 75.7804,
                'birth_timezone': 5.5,
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.data['data']
        self.assertEqual(data['time_of_birth'], '06:15')
        self.assertEqual(data['place_of_birth'], 'Kozhikode')
        self.assertAlmostEqual(float(data['birth_latitude']), 11.2588, places=3)

        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.time_of_birth, time(6, 15))
        self.assertEqual(profile.place_of_birth, 'Kozhikode')

        hp = HoroscopeProfile.objects.get(user=self.user)
        self.assertAlmostEqual(float(hp.pr_lat), 11.2588, places=3)
        self.assertAlmostEqual(float(hp.pr_lon), 75.7804, places=3)
        self.assertFalse(hp.is_calculated)
        self.assertIsNone(hp.calculated_at)

    def test_post_missing_place_returns_400(self):
        resp = self.client.post(
            '/api/v1/profile/birth-details/',
            {'time_of_birth': '10:30'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(
            UserProfile.objects.filter(user=self.user, has_horoscope=True).exists()
        )
