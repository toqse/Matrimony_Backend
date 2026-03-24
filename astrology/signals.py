import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from profiles.models import UserProfile

from .models import Horoscope
from .services.horoscope_service import generate_horoscope_payload
from .services.utils import build_birth_input_hash

logger = logging.getLogger(__name__)


@receiver(post_save, sender=UserProfile)
def auto_generate_horoscope(sender, instance, **kwargs):
    dob = getattr(instance.user, 'dob', None)
    tob = getattr(instance, 'time_of_birth', None)
    pob = getattr(instance, 'place_of_birth', '')
    if not dob or not tob or not pob:
        return

    birth_hash = build_birth_input_hash(dob, tob, pob)
    existing = Horoscope.objects.filter(profile=instance).only('id', 'birth_input_hash').first()
    if existing and existing.birth_input_hash == birth_hash:
        return

    try:
        payload = generate_horoscope_payload(
            date_of_birth=dob,
            time_of_birth=tob,
            place_of_birth=pob,
        )
        Horoscope.objects.update_or_create(profile=instance, defaults=payload)
    except Exception as exc:  # pragma: no cover - graceful signal failure
        logger.warning('Auto horoscope generation failed for profile=%s: %s', instance.pk, exc)
