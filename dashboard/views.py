"""
Dashboard APIs: summary, new-matches, suggestions, today-picks.
All require JWT authentication.
"""
from datetime import timedelta
from django.db.models import Q, IntegerField, Value
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.models import User
from profiles.models import UserLocation, UserReligion, UserPersonal, UserEducation, UserPhotos
from profiles.utils import get_profile_completion_data
from plans.models import ProfileView, Interest, UserPlan
from plans.services import _get_user_plan
from user_settings.models import UserSettings
from matches.utils import age_from_dob, compute_match_percentage
from core.media import absolute_media_url


def _match_queryset(user):
    """Base queryset: opposite gender, exclude self, active users."""
    qs = User.objects.filter(is_active=True).exclude(pk=user.pk)
    gender = getattr(user, 'gender', None)
    if gender == 'M':
        qs = qs.filter(gender='F')
    elif gender == 'F':
        qs = qs.filter(gender='M')
    completion_score = (
        Coalesce(Cast('user_profile__location_completed', IntegerField()), Value(0)) +
        Coalesce(Cast('user_profile__religion_completed', IntegerField()), Value(0)) +
        Coalesce(Cast('user_profile__personal_completed', IntegerField()), Value(0)) +
        Coalesce(Cast('user_profile__family_completed', IntegerField()), Value(0)) +
        Coalesce(Cast('user_profile__education_completed', IntegerField()), Value(0)) +
        Coalesce(Cast('user_profile__about_completed', IntegerField()), Value(0)) +
        Coalesce(Cast('user_profile__photos_completed', IntegerField()), Value(0))
    )
    # 6 of 7 completed steps => int((6/7) * 100) == 85
    return qs.annotate(profile_completion_steps=completion_score).filter(profile_completion_steps__gte=6)


def _apply_partner_preference(qs, user):
    """Apply viewer's partner religion/caste preference."""
    from profiles.models import UserReligion
    viewer_rel = UserReligion.objects.filter(user=user).first()
    if viewer_rel:
        pref_type = getattr(viewer_rel, 'partner_preference_type', None) or UserReligion.PARTNER_PREFERENCE_ALL
        if pref_type == UserReligion.PARTNER_PREFERENCE_OWN:
            if viewer_rel.religion_id:
                qs = qs.filter(user_religion__religion_id=viewer_rel.religion_id)
                if getattr(viewer_rel, 'partner_caste_preference', None) == UserReligion.PARTNER_CASTE_OWN and viewer_rel.caste_fk_id:
                    qs = qs.filter(user_religion__caste_fk_id=viewer_rel.caste_fk_id)
        elif pref_type == UserReligion.PARTNER_PREFERENCE_SPECIFIC:
            religion_ids = getattr(viewer_rel, 'partner_religion_ids', None) or []
            if religion_ids:
                qs = qs.filter(user_religion__religion_id__in=religion_ids)
            else:
                qs = qs.none()
    return qs


def _build_profile_card(request, user, viewer, include_extended=False):
    """Build profile card dict for dashboard lists."""
    from matches.utils import age_from_dob
    pers = getattr(user, 'user_personal', None) or UserPersonal.objects.filter(user=user).select_related('height').first()
    edu = getattr(user, 'user_education', None) or UserEducation.objects.filter(user=user).select_related(
        'highest_education', 'occupation'
    ).first()
    photos = getattr(user, 'user_photos', None) or UserPhotos.objects.filter(user=user).first()
    rel = getattr(user, 'user_religion', None) or UserReligion.objects.filter(user=user).select_related('religion').first()
    loc = getattr(user, 'user_location', None) or UserLocation.objects.filter(user=user).select_related('state', 'city').first()

    profile_photo = None
    if photos and photos.profile_photo:
        profile_photo = absolute_media_url(request, photos.profile_photo)

    location_str = None
    if loc:
        parts = []
        if loc.city:
            parts.append(loc.city.name)
        if loc.state:
            parts.append(loc.state.name)
        location_str = ', '.join(parts) if parts else None

    viewer_rel = UserReligion.objects.filter(user=viewer).select_related('religion', 'caste_fk').first()
    viewer_pers = UserPersonal.objects.filter(user=viewer).select_related('height', 'marital_status').first()
    viewer_edu = UserEducation.objects.filter(user=viewer).select_related('highest_education', 'occupation').first()
    viewer_loc = UserLocation.objects.filter(user=viewer).select_related('state', 'city').first()

    match_pct = compute_match_percentage(
        viewer, user,
        viewer_rel, viewer_pers, viewer_edu, viewer_loc,
        rel, pers, edu, loc
    )

    new_threshold = timezone.now() - timedelta(days=7)
    is_new = user.created_at >= new_threshold if user.created_at else False

    up = _get_user_plan(user)
    is_premium = up is not None and getattr(up, 'is_active', True)

    last_seen = getattr(user, 'last_seen', None)
    is_online = last_seen and (timezone.now() - last_seen) < timedelta(minutes=15) if last_seen else False

    card = {
        'matri_id': user.matri_id or '',
        'name': user.name or '',
        'age': age_from_dob(user.dob) if user.dob else None,
        'location': location_str,
        'profile_photo': profile_photo,
        'match_percentage': match_pct,
        'is_premium': is_premium,
        'is_new': is_new,
    }
    if include_extended:
        height_val = None
        if pers and pers.height_id and getattr(pers, 'height', None):
            height_val = pers.height.display_label or f"{pers.height.value_cm} cm"
        elif pers and getattr(pers, 'height_text', None):
            height_val = pers.height_text
        card.update({
            'education': edu.highest_education.name if edu and edu.highest_education_id else None,
            'occupation': edu.occupation.name if edu and edu.occupation_id else None,
            'height': height_val,
            'religion': rel.religion.name if rel and rel.religion_id else None,
            'is_online': is_online,
            'is_verified': user.mobile_verified if hasattr(user, 'mobile_verified') else False,
        })
    return card


class DashboardSummaryView(APIView):
    """
    GET /api/v1/dashboard/summary/
    Returns summary stats for dashboard header.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        completion = get_profile_completion_data(user)
        profile_completion = completion['profile_completion_percentage']

        loc = UserLocation.objects.filter(user=user).select_related('state', 'city').first()
        location_str = None
        if loc and loc.city:
            location_str = loc.city.name
        elif loc and loc.state:
            location_str = loc.state.name

        profile_views = ProfileView.objects.filter(viewed_user=user).count()
        interests_received = Interest.objects.filter(receiver=user).count()
        interests_sent = Interest.objects.filter(sender=user).count()

        qs = _match_queryset(user)
        qs = _apply_partner_preference(qs, user)
        qs = qs.exclude(user_settings__profile_visibility=UserSettings.PROFILE_VISIBILITY_HIDDEN)
        viewer_has_plan = _get_user_plan(user) is not None
        if not viewer_has_plan:
            qs = qs.exclude(user_settings__profile_visibility=UserSettings.PROFILE_VISIBILITY_PREMIUM)
        new_matches = qs.distinct().count()

        return Response({
            'success': True,
            'data': {
                'matri_id': user.matri_id or '',
                'profile_completion': profile_completion,
                'location': location_str or '',
                'profile_views': profile_views,
                'interests_received': interests_received,
                'interests_sent': interests_sent,
                'new_matches': new_matches,
            },
        }, status=status.HTTP_200_OK)


class NewMatchesView(APIView):
    """
    GET /api/v1/dashboard/new-matches/
    Query params: limit (default 4)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        try:
            limit = max(1, min(20, int(request.query_params.get('limit', 4))))
        except (TypeError, ValueError):
            limit = 4

        qs = _match_queryset(user)
        qs = _apply_partner_preference(qs, user)
        qs = qs.exclude(user_settings__profile_visibility=UserSettings.PROFILE_VISIBILITY_HIDDEN)
        viewer_has_plan = _get_user_plan(user) is not None
        if not viewer_has_plan:
            qs = qs.exclude(user_settings__profile_visibility=UserSettings.PROFILE_VISIBILITY_PREMIUM)
        qs = qs.select_related(
            'user_personal', 'user_personal__height',
            'user_religion', 'user_religion__religion',
            'user_education', 'user_education__highest_education', 'user_education__occupation',
            'user_photos', 'user_location', 'user_location__state', 'user_location__city',
        ).distinct().order_by('-created_at')[:limit]

        data = [_build_profile_card(request, u, user, include_extended=False) for u in qs]
        return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)


class SuggestionsView(APIView):
    """
    GET /api/v1/dashboard/suggestions/
    Suggest profiles based on partner preference, location, age range, education.
    Query params: limit (default 8)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        try:
            limit = max(1, min(50, int(request.query_params.get('limit', 8))))
        except (TypeError, ValueError):
            limit = 8

        qs = _match_queryset(user)
        qs = _apply_partner_preference(qs, user)
        qs = qs.exclude(user_settings__profile_visibility=UserSettings.PROFILE_VISIBILITY_HIDDEN)
        viewer_has_plan = _get_user_plan(user) is not None
        if not viewer_has_plan:
            qs = qs.exclude(user_settings__profile_visibility=UserSettings.PROFILE_VISIBILITY_PREMIUM)

        # Nearby matches: filter by same city (no coordinates).
        # If viewer city is not set, return empty suggestions (city-only mode).
        viewer_loc = UserLocation.objects.filter(user=user).select_related('city').first()
        if not viewer_loc or not viewer_loc.city_id:
            return Response({'success': True, 'data': []}, status=status.HTTP_200_OK)
        qs = qs.filter(user_location__city_id=viewer_loc.city_id)

        viewer_age = age_from_dob(user.dob) if user.dob else None
        if viewer_age is not None:
            from matches.utils import dob_range_for_age
            age_min = max(18, viewer_age - 5)
            age_max = min(80, viewer_age + 5)
            dob_min, dob_max = dob_range_for_age(age_min, age_max)
            if dob_min is not None:
                qs = qs.filter(dob__gte=dob_min)
            if dob_max is not None:
                qs = qs.filter(dob__lte=dob_max)

        qs = qs.select_related(
            'user_personal', 'user_personal__height',
            'user_religion', 'user_religion__religion',
            'user_education', 'user_education__highest_education', 'user_education__occupation',
            'user_photos', 'user_location', 'user_location__state', 'user_location__city',
        ).distinct().order_by('-created_at')[:limit]

        data = [_build_profile_card(request, u, user, include_extended=True) for u in qs]
        return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)


class TodayPicksView(APIView):
    """
    GET /api/v1/dashboard/today-picks/
    Returns curated profiles for today (recent profiles with photos).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        qs = _match_queryset(user)
        qs = _apply_partner_preference(qs, user)
        qs = qs.exclude(user_settings__profile_visibility=UserSettings.PROFILE_VISIBILITY_HIDDEN)
        viewer_has_plan = _get_user_plan(user) is not None
        if not viewer_has_plan:
            qs = qs.exclude(user_settings__profile_visibility=UserSettings.PROFILE_VISIBILITY_PREMIUM)
        qs = qs.filter(user_photos__profile_photo__isnull=False)
        qs = qs.select_related(
            'user_education', 'user_education__occupation',
            'user_photos',
        ).distinct().order_by('-created_at')[:6]

        data = []
        for u in qs:
            edu = getattr(u, 'user_education', None)
            photos = getattr(u, 'user_photos', None)
            profile_photo = None
            if photos and photos.profile_photo:
                profile_photo = absolute_media_url(request, photos.profile_photo)
            data.append({
                'matri_id': u.matri_id or '',
                'name': u.name or '',
                'age': age_from_dob(u.dob) if u.dob else None,
                'occupation': edu.occupation.name if edu and edu.occupation_id else None,
                'profile_photo': profile_photo,
            })
        return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)
