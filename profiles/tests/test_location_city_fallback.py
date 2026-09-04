"""City master vs manual city_name location validation."""
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from master.models import City, Country, District, State
from profiles.models import UserLocation


class LocationCityFallbackTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(mobile='9311111101', password='x', role='user')
        self.client.force_authenticate(user=self.user)

        self.country = Country.objects.create(name='India', code='IN', is_active=True)
        self.state = State.objects.create(country=self.country, name='Kerala', is_active=True)
        self.district = District.objects.create(state=self.state, name='Malappuram', is_active=True)
        self.other_district = District.objects.create(state=self.state, name='Kozhikode', is_active=True)
        self.city = City.objects.create(district=self.district, name='Nilambur', is_active=True)
        self.other_city = City.objects.create(
            district=self.other_district, name='Koyilandy', is_active=True
        )

    def _base(self, **extra):
        payload = {
            'country_id': self.country.id,
            'state_id': self.state.id,
            'district_id': self.district.id,
            'address': 'Test address',
        }
        payload.update(extra)
        return payload

    def test_master_city_post(self):
        resp = self.client.post(
            '/api/v1/profile/location/',
            self._base(city_id=self.city.id),
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        loc = UserLocation.objects.get(user=self.user)
        self.assertEqual(loc.city_id, self.city.id)
        self.assertEqual(loc.city_name, 'Nilambur')

    def test_manual_city_when_district_has_no_cities(self):
        empty = District.objects.create(state=self.state, name='EmptyDistrict', is_active=True)
        resp = self.client.post(
            '/api/v1/profile/location/',
            {
                'country_id': self.country.id,
                'state_id': self.state.id,
                'district_id': empty.id,
                'city_id': None,
                'city_name': 'Example City',
                'address': 'Addr',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        loc = UserLocation.objects.get(user=self.user)
        self.assertIsNone(loc.city_id)
        self.assertEqual(loc.city_name, 'Example City')
        self.assertFalse(City.objects.filter(district=empty).exists())

    def test_manual_unknown_city(self):
        resp = self.client.post(
            '/api/v1/profile/location/',
            self._base(city_id=None, city_name='Exampleville'),
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        loc = UserLocation.objects.get(user=self.user)
        self.assertIsNone(loc.city_id)
        self.assertEqual(loc.city_name, 'Exampleville')
        self.assertEqual(City.objects.filter(name__iexact='Exampleville').count(), 0)

    def test_cross_district_city_rejected(self):
        resp = self.client.post(
            '/api/v1/profile/location/',
            self._base(city_id=self.other_city.id),
            format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_patch_manual_city(self):
        UserLocation.objects.create(
            user=self.user,
            country=self.country,
            state=self.state,
            district=self.district,
            city=self.city,
            city_name='Nilambur',
            address='A',
        )
        resp = self.client.patch(
            '/api/v1/profile/location/',
            {
                'country_id': self.country.id,
                'state_id': self.state.id,
                'district_id': self.district.id,
                'city_id': None,
                'city_name': 'Manual Town',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        loc = UserLocation.objects.get(user=self.user)
        self.assertIsNone(loc.city_id)
        self.assertEqual(loc.city_name, 'Manual Town')
        data = resp.json()['data']
        self.assertEqual(data.get('city_source'), 'user')
        self.assertEqual(data.get('city_name'), 'Manual Town')

    def test_read_prefers_city_name(self):
        UserLocation.objects.create(
            user=self.user,
            country=self.country,
            state=self.state,
            district=self.district,
            city=None,
            city_name='Custom Place',
            address='A',
        )
        resp = self.client.get('/api/v1/profile/location/')
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()['data']
        self.assertIsNone(data.get('city_id'))
        self.assertEqual(data.get('city'), 'Custom Place')
        self.assertEqual(data.get('city_source'), 'user')

    def test_existing_master_city_still_reads(self):
        UserLocation.objects.create(
            user=self.user,
            country=self.country,
            state=self.state,
            district=self.district,
            city=self.city,
            city_name='Nilambur',
            address='A',
        )
        resp = self.client.get('/api/v1/profile/location/')
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()['data']
        self.assertEqual(data.get('city_id'), self.city.id)
        self.assertEqual(data.get('city_source'), 'master')
        self.assertEqual(data.get('city'), 'Nilambur')
