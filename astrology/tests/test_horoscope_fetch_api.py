"""Tests for horoscope fetch API EXE-generation gate."""

from datetime import date, time
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import User
from admin_panel.auth.models import AdminUser
from admin_panel.horoscope_mgmt.services import record_detail, scoped_member_users_queryset
from astrology.horoscope_api import (
    horoscope_fetch_payload,
    horoscope_not_found_response,
    horoscope_not_generated_response,
)
from astrology.models import HoroscopeProfile
from astrology.serializers import HoroscopeProfileSerializer
from astrology.views import HoroscopeProfileDetailView, HoroscopeProfileMeView
from master.models import Branch as MasterBranch
from profiles.models import UserProfile


LOCMEM_CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'horoscope-fetch-api-tests',
    }
}


def _rasi_string(moon_sign: int = 2) -> str:
    chars = []
    for i in range(11):
        if i == 2:
            chars.append(chr(ord('A') + moon_sign - 1))
        else:
            chars.append('A')
    return ''.join(chars)


class HoroscopeApiEnvelopeTests(TestCase):
    def test_not_found_envelope(self):
        payload = horoscope_not_found_response()
        self.assertFalse(payload['success'])
        self.assertFalse(payload['is_horoscope_generated'])
        self.assertEqual(payload['error']['code'], 404)

    def test_not_generated_envelope(self):
        payload = horoscope_not_generated_response()
        self.assertFalse(payload['success'])
        self.assertFalse(payload['is_horoscope_generated'])
        self.assertEqual(payload['error']['code'], 400)

    def test_fetch_payload_when_exe_done_includes_charts(self):
        hp = HoroscopeProfile(
            id=1,
            pr_rasi=_rasi_string(),
            pr_star=5,
            pr_pada=1,
        )
        payload = horoscope_fetch_payload(hp, serializer_class=HoroscopeProfileSerializer)
        self.assertTrue(payload['success'])
        self.assertTrue(payload['is_horoscope_generated'])
        self.assertIn('charts', payload['data'])


@override_settings(CACHES=LOCMEM_CACHES)
class HoroscopeProfileMeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            mobile='+919876543700',
            password='x',
            name='Horoscope Member',
        )
        self.user.is_active = True
        self.user.save()
        self.factory = APIRequestFactory()

    def _get(self, user=None):
        request = self.factory.get('/api/v1/astrology/horoscope/me/')
        force_authenticate(request, user=user or self.user)
        response = HoroscopeProfileMeView.as_view()(request)
        return response

    def test_no_profile_returns_not_found_envelope(self):
        HoroscopeProfile.objects.filter(user=self.user).delete()
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['success'])
        self.assertFalse(response.data['is_horoscope_generated'])
        self.assertEqual(response.data['error']['code'], 404)

    def test_profile_without_exe_outputs_returns_not_generated(self):
        hp, _ = HoroscopeProfile.objects.get_or_create(user=self.user)
        hp.pr_name = 'Horoscope Member'
        hp.pr_dob = date(1995, 1, 15)
        hp.pr_tob = time(10, 30)
        hp.pr_lat = 9.93
        hp.pr_lon = 76.27
        hp.pr_rasi = ''
        hp.pr_star = None
        hp.save()
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['success'])
        self.assertFalse(response.data['is_horoscope_generated'])
        self.assertEqual(response.data['error']['code'], 400)
        self.assertNotIn('data', response.data)

    def test_profile_with_exe_outputs_returns_full_data(self):
        hp, _ = HoroscopeProfile.objects.get_or_create(user=self.user)
        hp.pr_name = 'Horoscope Member'
        hp.pr_rasi = _rasi_string()
        hp.pr_star = 5
        hp.pr_pada = 2
        hp.save()
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertTrue(response.data['is_horoscope_generated'])
        self.assertIn('charts', response.data['data'])


@override_settings(CACHES=LOCMEM_CACHES)
class HoroscopeProfileDetailViewTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(
            mobile='+919876543701',
            password='x',
            name='Viewer',
        )
        self.target = User.objects.create_user(
            mobile='+919876543702',
            password='x',
            name='Target',
        )
        self.factory = APIRequestFactory()
        self.plan_patcher = patch(
            'astrology.views.get_user_plan_status',
            return_value='active',
        )
        self.plan_patcher.start()

    def tearDown(self):
        self.plan_patcher.stop()

    def _get(self, user_id):
        request = self.factory.get(f'/api/v1/astrology/horoscope/{user_id}/')
        force_authenticate(request, user=self.viewer)
        return HoroscopeProfileDetailView.as_view()(request, user_id=user_id)

    def test_missing_profile_returns_not_found_envelope(self):
        HoroscopeProfile.objects.filter(user=self.target).delete()
        response = self._get(self.target.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['success'])
        self.assertFalse(response.data['is_horoscope_generated'])

    def test_exe_done_returns_public_serializer_data(self):
        hp, _ = HoroscopeProfile.objects.get_or_create(user=self.target)
        hp.pr_rasi = _rasi_string()
        hp.pr_star = 3
        hp.pr_pada = 1
        hp.save()
        response = self._get(self.target.pk)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertTrue(response.data['is_horoscope_generated'])
        self.assertIn('charts', response.data['data'])


class HoroscopePanelRecordDetailTests(TestCase):
    def setUp(self):
        self.master_br = MasterBranch.objects.create(name='Detail Branch', code='HP_DT_01')
        self.member = User.objects.create_user(
            mobile='+919876543703',
            password='x',
            name='Detail Member',
            role='user',
        )
        self.member.is_active = True
        self.member.branch = self.master_br
        self.member.save()
        UserProfile.objects.get_or_create(user=self.member, defaults={})
        self.admin = AdminUser.objects.create(
            mobile='9000000100',
            name='Detail Admin',
            role=AdminUser.ROLE_ADMIN,
        )

    def test_record_detail_without_horoscope_marks_not_found(self):
        from types import SimpleNamespace

        HoroscopeProfile.objects.filter(user=self.member).delete()
        req = SimpleNamespace(user=self.admin)
        qs = scoped_member_users_queryset(req, mount='admin')
        data = record_detail(qs, self.member.pk)
        self.assertIsNotNone(data)
        self.assertIsNone(data['horoscope'])
        self.assertFalse(data['exe_pending'])

    def test_record_detail_with_pending_exe_marks_flag(self):
        from types import SimpleNamespace

        hp, _ = HoroscopeProfile.objects.get_or_create(user=self.member)
        hp.pr_name = 'Detail Member'
        hp.pr_dob = date(1990, 5, 5)
        hp.pr_tob = time(8, 0)
        hp.pr_lat = 10.0
        hp.pr_lon = 76.0
        hp.pr_rasi = ''
        hp.pr_star = None
        hp.save()
        req = SimpleNamespace(user=self.admin)
        qs = scoped_member_users_queryset(req, mount='admin')
        data = record_detail(qs, self.member.pk)
        self.assertIsNotNone(data)
        self.assertIsNone(data['horoscope'])
        self.assertTrue(data['exe_pending'])

    def test_record_detail_with_exe_done_includes_serializer(self):
        from types import SimpleNamespace

        hp, _ = HoroscopeProfile.objects.get_or_create(user=self.member)
        hp.pr_rasi = _rasi_string()
        hp.pr_star = 7
        hp.pr_pada = 3
        hp.pr_name = 'Detail Member'
        hp.save()
        req = SimpleNamespace(user=self.admin)
        qs = scoped_member_users_queryset(req, mount='admin')
        data = record_detail(qs, self.member.pk)
        self.assertIsNotNone(data)
        self.assertIsNotNone(data['horoscope'])
        self.assertFalse(data['exe_pending'])
        self.assertIn('charts', data['horoscope'])
