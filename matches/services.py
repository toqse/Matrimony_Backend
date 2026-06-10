"""
Match suggestion helpers for arbitrary target users (staff/admin panels).
"""
from __future__ import annotations

from django.db.models import Q

from accounts.models import User
from core.media import absolute_media_url
from profiles.models import UserReligion
from profiles.utils import filter_visible_profiles_queryset
from user_settings.models import UserSettings

from .utils import age_from_dob, build_user_match_score_sql_expression, dob_range_for_age


def apply_partner_preference(qs, viewer_rel):
    pref_type = getattr(viewer_rel, "partner_preference_type", None) or UserReligion.PARTNER_PREFERENCE_ALL
    caste_map = getattr(viewer_rel, "partner_caste_preferences", None) or {}
    normalized_caste_map = {}
    for key, value in caste_map.items():
        try:
            rid = int(str(key).strip())
        except (TypeError, ValueError):
            continue
        if isinstance(value, list):
            normalized_caste_map[rid] = [int(cid) for cid in value if str(cid).strip().isdigit()]

    if pref_type == UserReligion.PARTNER_PREFERENCE_OWN:
        if not viewer_rel.religion_id:
            return qs.none()
        qs = qs.filter(user_religion__religion_id=viewer_rel.religion_id)
        own_castes = normalized_caste_map.get(int(viewer_rel.religion_id), [])
        if own_castes:
            qs = qs.filter(user_religion__caste_fk_id__in=own_castes)
        return qs

    if pref_type == UserReligion.PARTNER_PREFERENCE_SPECIFIC:
        religion_ids = [int(x) for x in (getattr(viewer_rel, "partner_religion_ids", None) or [])]
        if not religion_ids:
            return qs.none()
        per_religion_q = Q()
        for religion_id in religion_ids:
            caste_ids = normalized_caste_map.get(religion_id, [])
            if caste_ids:
                per_religion_q |= Q(
                    user_religion__religion_id=religion_id,
                    user_religion__caste_fk_id__in=caste_ids,
                )
            else:
                per_religion_q |= Q(user_religion__religion_id=religion_id)
        return qs.filter(per_religion_q)

    return qs


def apply_partner_age_preference(qs, viewer_rel):
    age_min = getattr(viewer_rel, "partner_age_from", None)
    age_max = getattr(viewer_rel, "partner_age_to", None)
    if age_min is None and age_max is None:
        return qs
    dob_min, dob_max = dob_range_for_age(age_min, age_max)
    if dob_min is not None:
        qs = qs.filter(dob__gte=dob_min)
    if dob_max is not None:
        qs = qs.filter(dob__lte=dob_max)
    return qs


def match_queryset_for_user(target_user: User):
    """Active members, opposite gender, exclude self, visibility rules."""
    qs = User.objects.filter(is_active=True, role="user").exclude(pk=target_user.pk)
    gender = getattr(target_user, "gender", None)
    if gender == "M":
        qs = qs.filter(gender="F")
    elif gender == "F":
        qs = qs.filter(gender="M")
    return filter_visible_profiles_queryset(qs)


def build_matches_for_user(target_user: User, *, request=None, limit: int = 20) -> list[dict]:
    """
    Ranked match suggestions for target_user across the full member pool.
    """
    limit = max(1, min(50, int(limit or 20)))
    qs = match_queryset_for_user(target_user)

    viewer_rel = UserReligion.objects.filter(user=target_user).first()
    if viewer_rel:
        qs = apply_partner_preference(qs, viewer_rel)
        qs = apply_partner_age_preference(qs, viewer_rel)

    qs = qs.exclude(user_settings__profile_visibility=UserSettings.PROFILE_VISIBILITY_HIDDEN)
    qs = qs.distinct()

    match_expr = build_user_match_score_sql_expression(target_user)
    qs = qs.annotate(match_score=match_expr).order_by("-match_score", "pk")

    qs = qs.select_related(
        "user_personal",
        "user_personal__marital_status",
        "user_religion",
        "user_religion__religion",
        "user_religion__caste_fk",
        "user_photos",
        "user_profile",
    ).distinct()[:limit]

    results = []
    for u in qs:
        rel = getattr(u, "user_religion", None)
        pers = getattr(u, "user_personal", None)
        photos = getattr(u, "user_photos", None)
        profile = getattr(u, "user_profile", None)

        photo_url = None
        if photos and photos.profile_photo:
            photo_url = absolute_media_url(request, photos.profile_photo) if request else None

        match_pct = min(100, int(getattr(u, "match_score", 0) or 0))

        results.append(
            {
                "matri_id": u.matri_id or "",
                "name": u.name or "",
                "age": age_from_dob(u.dob) if u.dob else None,
                "gender": u.get_gender_display() if u.gender else "",
                "religion": rel.religion.name if rel and rel.religion_id else None,
                "caste": rel.caste_fk.name if rel and rel.caste_fk_id else None,
                "marital_status": pers.marital_status.name if pers and pers.marital_status_id else None,
                "match_percentage": match_pct,
                "admin_verified": bool(profile and profile.admin_verified),
                "profile_photo": photo_url,
            }
        )
    return results
