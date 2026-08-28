"""Porutham API consumes horoscope quota only on the first match of a pair."""

from datetime import date, timedelta

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import User
from astrology.models import HoroscopeProfile
from astrology.views import PoruthamCheckView
from plans.models import Plan, UserPlan


LOCMEM_CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'porutham-quota-tests',
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


def _make_exe_done_horoscope(user, star=5, pada=1, moon_sign=2):
    hp, _ = HoroscopeProfile.objects.update_or_create(
        user=user,
        defaults={
            'pr_rasi': _rasi_string(moon_sign),
            'pr_star': star,
            'pr_pada': pada,
            'pr_name': user.name,
            'pr_dob': date(2000, 1, 1),
        },
    )
    return hp


@override_settings(CACHES=LOCMEM_CACHES)
class PoruthamRematchQuotaTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.bride = User.objects.create_user(
            mobile='+919876543801',
            password='x',
            name='Bride Member',
            gender='F',
        )
        self.bride.is_active = True
        self.bride.save()
        self.groom = User.objects.create_user(
            mobile='+919876543802',
            password='x',
            name='Groom Member',
            gender='M',
        )
        self.groom.is_active = True
        self.groom.save()
        _make_exe_done_horoscope(self.bride, star=5, pada=4, moon_sign=3)
        _make_exe_done_horoscope(self.groom, star=7, pada=1, moon_sign=3)

        plan = Plan.objects.create(
            name='Gold Test',
            price=1,
            duration_days=30,
            horoscope_match_limit=1,
            is_active=True,
        )
        today = date.today()
        self.user_plan = UserPlan.objects.create(
            user=self.bride,
            plan=plan,
            is_active=True,
            valid_from=today,
            valid_until=today + timedelta(days=30),
            horoscope_used=0,
        )

    def _post(self):
        request = self.factory.post(
            '/api/v1/astrology/porutham/',
            {
                'matri_id': self.bride.matri_id,
                'partner_matri_id': self.groom.matri_id,
            },
            format='json',
        )
        force_authenticate(request, user=self.bride)
        return PoruthamCheckView.as_view()(request)

    def test_rematch_same_pair_does_not_consume_quota(self):
        first = self._post()
        self.assertEqual(first.status_code, 200)
        self.user_plan.refresh_from_db()
        self.assertEqual(self.user_plan.horoscope_used, 1)

        second = self._post()
        self.assertEqual(second.status_code, 200)
        self.user_plan.refresh_from_db()
        self.assertEqual(self.user_plan.horoscope_used, 1)

    def test_rematch_allowed_when_quota_is_exhausted(self):
        first = self._post()
        self.assertEqual(first.status_code, 200)
        self.user_plan.refresh_from_db()
        self.assertEqual(self.user_plan.horoscope_used, 1)

        rematch = self._post()
        self.assertEqual(rematch.status_code, 200)
        self.assertTrue(rematch.data.get('success'))
        self.user_plan.refresh_from_db()
        self.assertEqual(self.user_plan.horoscope_used, 1)
