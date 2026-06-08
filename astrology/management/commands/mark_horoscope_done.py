"""
Fill derived horoscope fields after the Windows EXE writes pr_rasi/pr_star/etc.

Uses the client's explicit reference tables for gana/yoni/rajju display values
(not the porutham matching engine).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from astrology.models import HoroscopeProfile

RASI_NAMES = [
    'Medam', 'Edavam', 'Midhunam', 'Kadakam', 'Chingam', 'Kanni',
    'Thulam', 'Vrischikam', 'Dhanu', 'Makaram', 'Kumbham', 'Meenam',
]

STAR_NAMES = [
    '', 'Ashwini', 'Bharani', 'Karthika', 'Rohini', 'Mrigasira',
    'Thiruvathira', 'Punartham', 'Pooyam', 'Ayilyam', 'Makam',
    'Pooram', 'Uthram', 'Atham', 'Chithra', 'Chothi', 'Vishakam',
    'Anizham', 'Thrikketta', 'Moolam', 'Pooradam', 'Uthradam',
    'Thiruvonam', 'Avittam', 'Chathayam', 'Pooruruttathi',
    'Uthuruttathi', 'Revathi',
]

DEVA_STARS = {1, 5, 7, 8, 13, 15, 17, 22, 27}
MANUSHA_STARS = {2, 4, 6, 11, 12, 20, 21, 25, 26}

STAR_YONI = [
    '', 'Ashwa', 'Gaja', 'Mesha', 'Sarpa', 'Sarpa', 'Swana', 'Marjara',
    'Mesha', 'Sarpa', 'Mushika', 'Gau', 'Gau', 'Mahisha', 'Vyaghra',
    'Mahisha', 'Vyaghra', 'Mriga', 'Swana', 'Mushika', 'Vanara',
    'Simha', 'Vanara', 'Simha', 'Ashwa', 'Gaja', 'Marjara', 'Mriga',
]

STAR_RAJJU = [
    '', 'Padam', 'Padam', 'Padam', 'Padam', 'Padam', 'Padam',
    'Kanda', 'Kanda', 'Kanda', 'Kanda', 'Kanda', 'Kanda',
    'Udara', 'Udara', 'Udara', 'Udara', 'Udara', 'Udara',
    'Kanda', 'Kanda', 'Kanda', 'Kanda', 'Kanda', 'Kanda',
    'Padam', 'Padam', 'Padam',
]

LETTER_INDEX = {c: i for i, c in enumerate('ABCDEFGHIJKL')}


def get_rasi_name(letter: str | None) -> str:
    idx = LETTER_INDEX.get((letter or '').upper())
    if idx is not None and idx < len(RASI_NAMES):
        return RASI_NAMES[idx]
    return ''


def get_gana(star_num: int | None) -> str:
    if not star_num:
        return ''
    if star_num in DEVA_STARS:
        return 'Deva'
    if star_num in MANUSHA_STARS:
        return 'Manusha'
    return 'Asura'


def fill_derived(profile: HoroscopeProfile) -> None:
    """Fill all derived fields from EXE output fields."""
    updates: dict = {}

    if profile.pr_rasi and len(profile.pr_rasi) >= 3:
        updates['lagnam'] = get_rasi_name(profile.pr_rasi[0])
        updates['rasi_sign'] = get_rasi_name(profile.pr_rasi[2])

    star = profile.pr_star
    if star and 1 <= star <= 27:
        updates['star_name'] = STAR_NAMES[star]
        updates['gana'] = get_gana(star)
        updates['yoni'] = STAR_YONI[star]
        updates['rajju'] = STAR_RAJJU[star]

    if profile.pr_pada:
        updates['nakshatra_pada'] = profile.pr_pada

    updates['is_calculated'] = True
    updates['calculated_at'] = timezone.now()

    HoroscopeProfile.objects.filter(pk=profile.pk).update(**updates)


class Command(BaseCommand):
    help = 'Fill derived horoscope fields for all rows written by the Windows EXE'

    def handle(self, *args, **options):
        qs = HoroscopeProfile.objects.filter(
            is_calculated=False,
            pr_rasi__isnull=False,
        ).exclude(pr_rasi='')

        total = qs.count()
        self.stdout.write(f'Found {total} rows to process...')

        done = 0
        errors = 0
        for profile in qs.iterator(chunk_size=100):
            try:
                if not profile.pr_rasi or len(profile.pr_rasi) < 3:
                    continue
                fill_derived(profile)
                from profiles.models import UserProfile

                UserProfile.objects.filter(user_id=profile.user_id).update(
                    has_horoscope=True
                )
                done += 1
            except Exception as exc:
                self.stderr.write(f'Error on id={profile.pk}: {exc}')
                errors += 1

        self.stdout.write(
            self.style.SUCCESS(f'Done. Processed={done}, Errors={errors}')
        )
