"""Gender-based default profile/full photos for create, edit, and backfill."""
from __future__ import annotations

from pathlib import Path

from django.core.files.base import ContentFile
from django.db.models import Q

from profiles.models import UserPhotos
from profiles.utils import sync_profile_completion_flags

DEFAULT_PHOTOS_DIR = Path(__file__).resolve().parent

GENDER_DEFAULT_FILES = {
    "M": {
        "profile_photo": "aiswarya_male_profile.png",
        "full_photo": "aiswarya_male_full.png",
    },
    "F": {
        "profile_photo": "aiswarya_female_profile.png",
        "full_photo": "aiswarya_female_full.png",
    },
}


def _image_field_empty(field) -> bool:
    return not bool(getattr(field, "name", "") or field)


def _empty_image_q(field: str) -> Q:
    return Q(**{f"user_photos__{field}__isnull": True}) | Q(**{f"user_photos__{field}": ""})


def users_needing_default_photos():
    """Members who would receive at least one gender default photo."""
    from accounts.models import User

    empty_url = Q(user_photos__profile_photo_url__isnull=True) | Q(user_photos__profile_photo_url="")
    return (
        User.objects.filter(gender__in=["M", "F"])
        .filter(
            Q(user_photos__isnull=True)
            | _empty_image_q("full_photo")
            | (_empty_image_q("profile_photo") & empty_url)
        )
        .distinct()
    )


def apply_gender_default_photos(user) -> bool:
    """Fill empty profile_photo / full_photo from gender defaults. Never overwrite uploads."""
    gender = (getattr(user, "gender", None) or "").strip().upper()
    files = GENDER_DEFAULT_FILES.get(gender)
    if not files:
        return False

    photos, _ = UserPhotos.objects.get_or_create(user=user)
    updated = False
    has_profile_url = bool((photos.profile_photo_url or "").strip())
    for attr, filename in files.items():
        if not _image_field_empty(getattr(photos, attr)):
            continue
        if attr == "profile_photo" and has_profile_url:
            continue
        path = DEFAULT_PHOTOS_DIR / filename
        if not path.is_file():
            continue
        setattr(photos, attr, ContentFile(path.read_bytes(), name=filename))
        updated = True

    if updated:
        photos.save()
        sync_profile_completion_flags(user)
        user.__dict__["user_photos"] = photos
    return updated
