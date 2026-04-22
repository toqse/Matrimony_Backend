"""
Shared horoscope load/refresh from UserProfile birth fields.

Used by member astrology APIs and admin/staff/branch panel APIs so logic stays identical.
"""

from profiles.models import UserProfile

from ..models import Horoscope
from .horoscope_service import generate_horoscope_payload
from .utils import build_birth_input_hash


def profile_birth_inputs(profile: UserProfile):
    dob = getattr(profile.user, 'dob', None)
    tob = getattr(profile, 'time_of_birth', None)
    pob = getattr(profile, 'place_of_birth', '')
    if not dob or not tob or not pob:
        return None
    return dob, tob, pob


def create_or_update_horoscope(profile: UserProfile):
    birth_inputs = profile_birth_inputs(profile)
    if not birth_inputs:
        raise ValueError('Profile birth details are incomplete.')

    dob, tob, pob = birth_inputs
    payload = generate_horoscope_payload(dob, tob, pob)
    horoscope, _ = Horoscope.objects.update_or_create(
        profile=profile,
        defaults=payload,
    )
    return horoscope


def resolve_horoscope_for_profile(profile: UserProfile) -> Horoscope:
    """
    Load stored horoscope or create/refresh from profile birth inputs.
    Raises ValueError('Birth details not available.') if no row exists and inputs are incomplete.
    """
    horoscope = Horoscope.objects.filter(profile=profile).first()
    birth_inputs = profile_birth_inputs(profile)
    if horoscope is None:
        if not birth_inputs:
            raise ValueError('Birth details not available.')
        return create_or_update_horoscope(profile)
    if birth_inputs:
        dob, tob, pob = birth_inputs
        current_hash = build_birth_input_hash(dob, tob, pob)
        if horoscope.birth_input_hash != current_hash:
            return create_or_update_horoscope(profile)
    return horoscope
