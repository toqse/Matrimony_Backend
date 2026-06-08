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
    Keeps HoroscopeProfile input fields in sync when member updates
    their birth time or birth place coordinates.
    Never overwrites EXE output fields (pr_rasi, pr_star, etc.).
    """
    from .models import HoroscopeProfile

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
        changed = any(getattr(hp, k) != v for k, v in updates.items())
        if changed:
            for k, v in updates.items():
                setattr(hp, k, v)
            hp.is_calculated = False
            hp.save(
                update_fields=list(updates.keys()) + ['is_calculated', 'updated_at']
            )
    except Exception as exc:
        logger.warning(
            'sync_birth_to_horoscope_profile failed user=%s: %s', user.pk, exc
        )
