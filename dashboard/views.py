"""
Dashboard APIs: summary, new-matches, suggestions, today-picks.
All require JWT authentication.
"""
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.models import User
from profiles.models import UserLocation, UserReligion, UserPersonal, UserEducation, UserPhotos
from profiles.utils import get_profile_completion_data, filter_visible_profiles_queryset
from plans.models import ProfileView, Interest
from plans.services import _get_user_plan, get_plan_info_for_response
from matches.rotation import annotate_daily_rotation_rank
from matches.services import (
    apply_partner_age_preference,
    apply_partner_preference,
    apply_profile_visibility_for_viewer,
    count_unique_match_profiles,
    preferred_match_queryset,
)
from matches.utils import age_from_dob, compute_match_percentage
from core.media import absolute_media_url


def _parse_page_params(request, default_page_size=8, max_page_size=50):
    try:
        page = max(1, int(request.query_params.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    raw_page_size = request.query_params.get('page_size')
    if raw_page_size is None:
        raw_page_size = request.query_params.get('limit', default_page_size)
    try:
        page_size = int(raw_page_size)
    except (TypeError, ValueError):
        page_size = default_page_size
    page_size = max(1, min(max_page_size, page_size))
    return page, page_size


def _match_queryset(user):
    """Base queryset: opposite gender, exclude self, active users."""
    qs = User.objects.filter(is_active=True).exclude(pk=user.pk)
    gender = getattr(user, 'gender', None)
    if gender == 'M':
        qs = qs.filter(gender='F')
    elif gender == 'F':
        qs = qs.filter(gender='M')
    return filter_visible_profiles_queryset(qs)


def _apply_partner_preference(qs, user):
    """Apply viewer's saved partner religion/caste and age (same as unfiltered My Matches)."""
    viewer_rel = UserReligion.objects.filter(user=user).first()
    if not viewer_rel:
        return qs
    qs = apply_partner_preference(qs, viewer_rel)
    qs = apply_partner_age_preference(qs, viewer_rel)
    return qs


def _load_viewer_match_context(viewer):
    """Load viewer profile sections once for match % (avoid per-card re-queries)."""
    return {
        'rel': UserReligion.objects.filter(user=viewer).select_related('religion', 'caste_fk').first(),
        'pers': UserPersonal.objects.filter(user=viewer).select_related('height', 'marital_status').first(),
        'edu': UserEducation.objects.filter(user=viewer).select_related('highest_education', 'occupation').first(),
        'loc': UserLocation.objects.filter(user=viewer).select_related('state', 'city').first(),
    }


_CARD_SELECT_RELATED = (
    'user_personal', 'user_personal__height',
    'user_religion', 'user_religion__religion',
    'user_education', 'user_education__highest_education', 'user_education__occupation',
    'user_photos', 'user_location', 'user_location__state', 'user_location__city',
    'user_plan', 'user_plan__plan',
)


def _build_profile_card(request, user, viewer, include_extended=False, viewer_ctx=None):
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
    full_photo = None
    if photos and photos.full_photo:
        full_photo = absolute_media_url(request, photos.full_photo)

    location_str = None
    if loc:
        parts = []
        if loc.city:
            parts.append(loc.city.name)
        if loc.state:
            parts.append(loc.state.name)
        location_str = ', '.join(parts) if parts else None

    if viewer_ctx is None:
        viewer_ctx = _load_viewer_match_context(viewer)
    viewer_rel = viewer_ctx['rel']
    viewer_pers = viewer_ctx['pers']
    viewer_edu = viewer_ctx['edu']
    viewer_loc = viewer_ctx['loc']

    match_pct = compute_match_percentage(
        viewer, user,
        viewer_rel, viewer_pers, viewer_edu, viewer_loc,
        rel, pers, edu, loc
    )

    new_threshold = timezone.now() - timedelta(days=7)
    is_new = user.created_at >= new_threshold if user.created_at else False

    # Prefer select_related user_plan; _get_user_plan uses the cached reverse relation.
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
        'full_photo': full_photo,
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

    new_matches is the unfiltered My Matches total (saved partner prefs + visibility),
    so it matches GET /api/v1/matches/ total_profiles when no extra sidebar filters are applied.
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

        profile_views = ProfileView.objects.filter(profile__user=user).count()
        interests_received = Interest.objects.filter(receiver=user).count()
        interests_sent = Interest.objects.filter(sender=user).count()

        qs = preferred_match_queryset(user)
        new_matches = count_unique_match_profiles(qs)

        plan = get_plan_info_for_response(user)

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
                'plan': plan,
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

        qs = preferred_match_queryset(user)
        qs = qs.select_related(*_CARD_SELECT_RELATED)
        qs = annotate_daily_rotation_rank(qs).order_by('daily_rotation_rank', 'pk')[:limit]

        viewer_ctx = _load_viewer_match_context(user)
        data = [
            _build_profile_card(request, u, user, include_extended=False, viewer_ctx=viewer_ctx)
            for u in qs
        ]
        return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)


class SuggestionsView(APIView):
    """
    GET /api/v1/dashboard/suggestions/
    Suggest profiles based on partner preference, location, age range, education.
    Query params: page (default 1), page_size (default 8), limit alias supported
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        page, page_size = _parse_page_params(request, default_page_size=8, max_page_size=50)

        qs = _match_queryset(user)
        qs = _apply_partner_preference(qs, user)
        qs = apply_profile_visibility_for_viewer(qs, user)

        # Nearby matches: filter by same city (no coordinates).
        # If viewer city is not set, return empty suggestions (city-only mode).
        viewer_ctx = _load_viewer_match_context(user)
        viewer_loc = viewer_ctx['loc']
        if not viewer_loc or not viewer_loc.city_id:
            return Response({
                'success': True,
                'data': {
                    'total': 0,
                    'page': page,
                    'page_size': page_size,
                    'limit': page_size,
                    'results': [],
                },
            }, status=status.HTTP_200_OK)
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

        qs = qs.select_related(*_CARD_SELECT_RELATED).distinct()
        qs = annotate_daily_rotation_rank(qs).order_by('daily_rotation_rank', 'pk')
        total = count_unique_match_profiles(qs)
        start = (page - 1) * page_size
        page_qs = qs[start:start + page_size]

        data = [
            _build_profile_card(request, u, user, include_extended=True, viewer_ctx=viewer_ctx)
            for u in page_qs
        ]
        return Response({
            'success': True,
            'data': {
                'total': total,
                'page': page,
                'page_size': page_size,
                'limit': page_size,
                'results': data,
            },
        }, status=status.HTTP_200_OK)


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
        qs = apply_profile_visibility_for_viewer(qs, user)
        qs = qs.filter(user_photos__profile_photo__isnull=False)
        qs = qs.select_related(
            'user_education', 'user_education__occupation',
            'user_photos',
        ).distinct()
        qs = annotate_daily_rotation_rank(qs).order_by('daily_rotation_rank', 'pk')[:6]

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
