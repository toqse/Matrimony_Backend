import logging

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from profiles.models import UserProfile

logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_horoscope_profile_on_register(sender, instance, created, **kwargs):
    """Create empty HoroscopeProfile row when a new user registers."""
    if not created:
        return
    from .models import HoroscopeProfile

    try:
        HoroscopeProfile.objects.get_or_create(
            user=instance,
            defaults={
                'pr_name': instance.name or '',
                'pr_dob': getattr(instance, 'dob', None),
                'pr_tz': 5.5,
            },
        )
    except Exception as exc:
        logger.warning(
            'create_horoscope_profile_on_register failed: %s', exc
        )


@receiver(post_save, sender=UserProfile)
def sync_birth_to_horoscope_profile(sender, instance, **kwargs):
    """
    Keep HoroscopeProfile input fields in sync when birth time or coordinates
    change. If those chart inputs change, clear EXE outputs so the generator
    rewrites the chart and GET horoscope/me does not serve the old one.
    """
    from .models import HoroscopeProfile
    from astrology.services.horoscope_profile_service import (
        EXE_OUTPUT_RESET,
        horoscope_chart_inputs_changed,
    )

    user = instance.user
    try:
        hp, _ = HoroscopeProfile.objects.get_or_create(
            user=user,
            defaults={
                'pr_name': user.name or '',
                'pr_dob': getattr(user, 'dob', None),
                'pr_tz': 5.5,
            },
        )
        profile_tz = getattr(instance, 'birth_timezone', None)
        updates = {
            'pr_name': user.name or '',
            'pr_dob': getattr(user, 'dob', None),
            'pr_tob': getattr(instance, 'time_of_birth', None),
            'pr_lat': getattr(instance, 'birth_latitude', None),
            'pr_lon': getattr(instance, 'birth_longitude', None),
        }
        if profile_tz is not None:
            updates['pr_tz'] = profile_tz
        changed = horoscope_chart_inputs_changed(
            hp,
            dob=updates['pr_dob'],
            birth_time=updates['pr_tob'],
            birth_latitude=updates['pr_lat'],
            birth_longitude=updates['pr_lon'],
            birth_timezone=updates.get('pr_tz', hp.pr_tz),
        )
        name_or_other = any(getattr(hp, k) != v for k, v in updates.items())
        if not changed and not name_or_other:
            return
        for k, v in updates.items():
            setattr(hp, k, v)
        update_fields = list(updates.keys()) + ['updated_at']
        if changed:
            hp.is_calculated = False
            hp.calculated_at = None
            for k, v in EXE_OUTPUT_RESET.items():
                setattr(hp, k, v)
            update_fields.extend(
                ['is_calculated', 'calculated_at', *EXE_OUTPUT_RESET.keys()]
            )
        hp.save(update_fields=update_fields)
    except Exception as exc:
        logger.warning(
            'sync_birth_to_horoscope_profile failed user=%s: %s', user.pk, exc
        )
