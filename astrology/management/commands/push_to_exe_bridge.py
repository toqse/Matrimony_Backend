from django.core.management.base import BaseCommand

from astrology.models import HoroscopeProfile
from profiles.models import UserProfile


class Command(BaseCommand):
    help = 'Push birth data to horoscope_profile for Windows EXE'

    def handle(self, *args, **options):
        qs = UserProfile.objects.select_related('user').filter(
            user__dob__isnull=False,
            time_of_birth__isnull=False,
            birth_latitude__isnull=False,
            birth_longitude__isnull=False,
        )
        count = 0
        for p in qs.iterator(chunk_size=200):
            u = p.user
            HoroscopeProfile.objects.update_or_create(
                user=u,
                defaults={
                    'pr_name': u.name or '',
                    'pr_dob': u.dob,
                    'pr_tob': p.time_of_birth,
                    'pr_lat': p.birth_latitude,
                    'pr_lon': p.birth_longitude,
                    'pr_tz': 5.5,
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f'Pushed {count} profiles to horoscope_profile.'))
