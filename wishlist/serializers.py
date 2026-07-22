from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from accounts.models import User
from matches.utils import age_from_dob
from matches.serializers import format_last_seen
from core.media import absolute_media_url
from .models import Wishlist


def _safe_one_to_one(obj, rel_name):
    try:
        return getattr(obj, rel_name)
    except ObjectDoesNotExist:
        return None


class WishlistSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wishlist
        fields = ['id', 'user', 'profile', 'created_at']
        read_only_fields = ['id', 'user', 'profile', 'created_at']


class WishlistProfileSerializer(serializers.Serializer):
    """
    One profile entry in wishlist list.
    Mirrors match card fields needed on My Matches page.
    """

    matri_id = serializers.CharField()
    name = serializers.CharField()
    age = serializers.IntegerField(allow_null=True)
    location = serializers.CharField(allow_null=True)
    education = serializers.CharField(allow_null=True)
    occupation = serializers.CharField(allow_null=True)
    profile_photo = serializers.CharField(allow_null=True)
    match_percentage = serializers.IntegerField(allow_null=True)
    is_online = serializers.BooleanField()
    last_seen = serializers.CharField(allow_null=True)


def _build_wishlist_profile_dict(viewer: User, profile_user: User, request=None) -> dict:
    """
    Build the wishlist card data for a single profile user.
    Reuses existing profile-related models; computes:
    - age, location, education, occupation, profile_photo, is_online, last_seen.
    match_percentage is left to the view to compute (so it can reuse
    compute_match_percentage with already-fetched related objects).
    """
    # Age
    age = age_from_dob(getattr(profile_user, 'dob', None))

    # Location / education / photos: use prefetched select_related when present (no N+1)
    loc = _safe_one_to_one(profile_user, 'user_location')
    city = getattr(getattr(loc, 'city', None), 'name', None)
    state = getattr(getattr(loc, 'state', None), 'name', None)
    if city and state:
        location = f'{city}, {state}'
    else:
        location = city or state or None

    edu = _safe_one_to_one(profile_user, 'user_education')
    education = getattr(getattr(edu, 'highest_education', None), 'name', None)
    occupation = getattr(getattr(edu, 'occupation', None), 'name', None)

    photos = _safe_one_to_one(profile_user, 'user_photos')
    if photos and photos.profile_photo:
        profile_photo = absolute_media_url(request, photos.profile_photo)
    else:
        profile_photo = None

    # Online / last seen
    last_seen_dt = getattr(profile_user, 'last_seen', None)
    is_online = False
    if last_seen_dt:
        from django.utils import timezone
        from datetime import timedelta

        is_online = (timezone.now() - last_seen_dt) < timedelta(minutes=15)

    return {
        'matri_id': profile_user.matri_id or '',
        'name': profile_user.name or '',
        'age': age,
        'location': location,
        'education': education,
        'occupation': occupation,
        'profile_photo': profile_photo,
        'match_percentage': None,  # filled in by caller
        'is_online': is_online,
        'last_seen': format_last_seen(last_seen_dt) if last_seen_dt else None,
    }

