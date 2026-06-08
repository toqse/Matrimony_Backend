from django.test import TestCase

from accounts.models import User
from astrology.management.commands.mark_horoscope_done import (
    fill_derived,
    get_gana,
    get_rasi_name,
)
from astrology.models import HoroscopeProfile


class MarkHoroscopeDerivedTests(TestCase):
    def test_get_rasi_name(self):
        self.assertEqual(get_rasi_name('A'), 'Medam')
        self.assertEqual(get_rasi_name('E'), 'Chingam')

    def test_get_gana_makam_is_asura(self):
        self.assertEqual(get_gana(10), 'Asura')

    def test_fill_derived_record_7928_fields(self):
        user = User.objects.create_user(
            mobile='9999907928',
            password='x',
            name='test10133',
        )
        hp, _ = HoroscopeProfile.objects.update_or_create(
            user=user,
            defaults={
                'pr_rasi': 'AGEEHKGAEKJ',
                'pr_star': 10,
                'pr_pada': 1,
                'pr_dasabalance': 2459,
                'is_calculated': False,
            },
        )
        fill_derived(hp)
        hp.refresh_from_db()

        self.assertEqual(hp.lagnam, 'Medam')
        self.assertEqual(hp.rasi_sign, 'Chingam')
        self.assertEqual(hp.star_name, 'Makam')
        self.assertEqual(hp.nakshatra_pada, 1)
        self.assertEqual(hp.gana, 'Asura')
        self.assertEqual(hp.yoni, 'Mushika')
        self.assertEqual(hp.rajju, 'Kanda')
        self.assertTrue(hp.is_calculated)
        self.assertIsNotNone(hp.calculated_at)
