"""
Match list API and Filter options API.
"""
from django.db.models import Q, Exists, OuterRef, F, Subquery, DateTimeField
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.models import User
from profiles.models import UserLocation, UserReligion, UserPersonal, UserEducation, UserPhotos
from profiles.utils import (
    apply_height_cm_range,
    filter_visible_profiles_queryset,
    height_cm_from_personal,
)
from plans.models import Interest, ProfileView as ProfileViewModel
from plans.services import (
    bulk_interest_ui_states_for_viewer,
    can_view_profile,
    can_send_interest,
    can_chat,
    user_has_active_plan,
)
from wishlist.models import Wishlist

from .services import (
    apply_partner_age_preference,
    apply_partner_preference,
    apply_profile_visibility_for_viewer,
    count_unique_match_profiles,
)
from .rotation import annotate_daily_rotation_rank
from .utils import age_from_dob, dob_range_for_age, build_user_match_score_sql_expression
from .serializers import MatchListProfileSerializer, format_last_seen
from core.media import absolute_media_url


def _optional_fk_id(raw):
    """Parse query id for filters; treat '', 0, 'any' as unset (no filter)."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s or s in ('0', 'any', 'null', 'none'):
        return None
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _optional_fk_id_list(request, *param_names):
    """Parse comma-separated or repeated query params into a deduped int list."""
    seen = set()
    ids = []
    for name in param_names:
        for raw in request.query_params.getlist(name):
            if raw is None:
                continue
            for part in str(raw).split(','):
                s = part.strip().lower()
                if not s or s in ('0', 'any', 'null', 'none'):
                    continue
                try:
                    val = int(s)
                except (TypeError, ValueError):
                    continue
                if val not in seen:
                    seen.add(val)
                    ids.append(val)
    return ids


def _wants_profile_with_photo(request):
    v = request.query_params.get('profile_with_photo')
    if v is None:
        return False
    return str(v).strip().lower() in ('1', 'true', 'yes', 'on')


def _match_queryset(request):
    """Build base queryset for matches: correct gender, exclude self, active users."""
    user = request.user
    qs = User.objects.filter(is_active=True).exclude(pk=user.pk)
    gender = getattr(user, 'gender', None)
    if gender == 'M':
        qs = qs.filter(gender='F')
    elif gender == 'F':
        qs = qs.filter(gender='M')
    # 'O' -> both, no filter
    return filter_visible_profiles_queryset(qs)


def _match_list_response(request, *, home_slider=False):
    """
    Shared match list payload. If home_slider is True: unviewed first, then viewed, then -created_at.
    Otherwise: order by sort_by only (no is_viewed in ORDER BY).
    """
    qs = _match_queryset(request)

    # Parse age / religion / caste query params once (explicit filters override saved prefs)
    try:
        age_min = int(request.query_params.get('age_min')) if request.query_params.get('age_min') else None
    except (TypeError, ValueError):
        age_min = None
    try:
        age_max = int(request.query_params.get('age_max')) if request.query_params.get('age_max') else None
    except (TypeError, ValueError):
        age_max = None
    has_age_filter = age_min is not None or age_max is not None

    religion_id = _optional_fk_id(request.query_params.get('religion_id'))
    caste_ids = _optional_fk_id_list(request, 'caste_ids', 'caste_id')
    education_ids = _optional_fk_id_list(request, 'education_ids', 'education_id')
    occupation_ids = _optional_fk_id_list(request, 'occupation_ids', 'occupation_id')
    has_religion_caste_filter = religion_id is not None or bool(caste_ids)

    # Saved partner preferences apply only when the corresponding query param is absent
    viewer_rel = UserReligion.objects.filter(user=request.user).first()
    if viewer_rel:
        if not has_religion_caste_filter:
            qs = apply_partner_preference(qs, viewer_rel)
        if not has_age_filter:
            qs = apply_partner_age_preference(qs, viewer_rel)
    qs = apply_profile_visibility_for_viewer(qs, request.user)
    qs = qs.distinct()

    # Search: name, matri_id, education, occupation
    search = request.query_params.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(matri_id__icontains=search) |
            Q(user_education__highest_education__name__icontains=search) |
            Q(user_education__occupation__name__icontains=search)
        ).distinct()

    # Age filter (explicit query params only; saved preference applied above when absent)
    if has_age_filter:
        dob_min, dob_max = dob_range_for_age(age_min, age_max)
        if dob_min is not None:
            qs = qs.filter(dob__gte=dob_min)
        if dob_max is not None:
            qs = qs.filter(dob__lte=dob_max)

    # Height filter: Height FK value_cm, else parsed height_text (e.g. "165 cm")
    try:
        height_min = int(request.query_params.get('height_min')) if request.query_params.get('height_min') else None
    except (TypeError, ValueError):
        height_min = None
    try:
        height_max = int(request.query_params.get('height_max')) if request.query_params.get('height_max') else None
    except (TypeError, ValueError):
        height_max = None
    qs = apply_height_cm_range(qs, height_min, height_max)

    # Optional filters (FK ids; skip 0/any so "Any" in UI does not filter to id=0)
    if religion_id is not None:
        qs = qs.filter(user_religion__religion_id=religion_id)
    if caste_ids:
        qs = qs.filter(user_religion__caste_fk_id__in=caste_ids)
    if education_ids:
        qs = qs.filter(user_education__highest_education_id__in=education_ids)
    if occupation_ids:
        qs = qs.filter(user_education__occupation_id__in=occupation_ids)
    marital_status_id = _optional_fk_id(request.query_params.get('marital_status'))
    if marital_status_id is not None:
        qs = qs.filter(user_personal__marital_status_id=marital_status_id)

    country_id = _optional_fk_id(request.query_params.get('country_id'))
    if country_id is not None:
        qs = qs.filter(user_location__country_id=country_id)
    state_id = _optional_fk_id(request.query_params.get('state_id'))
    if state_id is not None:
        qs = qs.filter(user_location__state_id=state_id)
    city_ids = _optional_fk_id_list(request, 'city_ids', 'city_id')
    district_ids = _optional_fk_id_list(request, 'district_ids', 'district_id')
    if city_ids:
        qs = qs.filter(user_location__city_id__in=city_ids)
    elif district_ids:
        qs = qs.filter(user_location__district_id__in=district_ids)

    # Only with profile photo
    if _wants_profile_with_photo(request):
        qs = qs.filter(user_photos__profile_photo__isnull=False)

    qs = qs.distinct()
    # Count unique users before score/rotation annotations (those add JOINs that inflate COUNT).
    total = count_unique_match_profiles(qs)

    viewed_subq = ProfileViewModel.objects.filter(
        viewer=request.user,
        profile__user_id=OuterRef('pk'),
    )
    unlocked_subq = ProfileViewModel.objects.filter(
        viewer=request.user,
        profile__user_id=OuterRef('pk'),
        unlocked=True,
    )
    match_expr = build_user_match_score_sql_expression(request.user)
    qs = qs.annotate(
        is_viewed=Exists(viewed_subq),
        is_unlocked=Exists(unlocked_subq),
        match_score=match_expr,
    )
    qs = qs.annotate(relevance_score=F('match_score'))

    qs = annotate_daily_rotation_rank(qs)

    if home_slider:
        qs = qs.annotate(
            view_last_at=Subquery(
                ProfileViewModel.objects.filter(
                    viewer=request.user,
                    profile__user_id=OuterRef('pk'),
                ).values('last_viewed_at')[:1],
                output_field=DateTimeField(),
            ),
        )
        # Unviewed first; among viewed, oldest view first; then daily rotation within each group.
        qs = qs.order_by('is_viewed', 'view_last_at', 'daily_rotation_rank', 'pk')
    else:
        sort_by = request.query_params.get('sort_by', 'newest')
        if sort_by == 'newest':
            qs = qs.order_by('daily_rotation_rank', 'pk')
        elif sort_by == 'best_match':
            qs = qs.order_by('-match_score', 'daily_rotation_rank', 'pk')
        elif sort_by == 'most_relevant':
            qs = qs.order_by('-relevance_score', 'daily_rotation_rank', 'pk')
        else:
            qs = qs.order_by('daily_rotation_rank', 'pk')

    # Pagination
    try:
        page = max(1, int(request.query_params.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        limit = max(1, min(50, int(request.query_params.get('limit', 10))))
    except (TypeError, ValueError):
        limit = 10
    start = (page - 1) * limit
    qs = qs.select_related(
        'user_personal', 'user_personal__height', 'user_personal__marital_status',
        'user_religion', 'user_religion__religion', 'user_religion__caste_fk',
        'user_education', 'user_education__highest_education', 'user_education__occupation',
        'user_photos', 'user_location', 'user_location__city', 'user_location__state',
    ).distinct()[start:start + limit]

    page_users = list(qs)
    page_user_ids = [u.pk for u in page_users]
    interest_ui_by_other_id = bulk_interest_ui_states_for_viewer(request.user.pk, page_user_ids)

    # Plan permissions for viewer (first-time full view quota)
    has_plan = user_has_active_plan(request.user)
    can_view, _ = can_view_profile(request.user)
    can_send, _ = can_send_interest(request.user)
    can_chat_flag, _ = can_chat(request.user)

    accepted_pair_rows = Interest.objects.filter(
        Q(sender=request.user, receiver_id__in=page_user_ids)
        | Q(receiver=request.user, sender_id__in=page_user_ids),
        status=Interest.STATUS_ACCEPTED,
    ).values_list('sender_id', 'receiver_id')
    uid = request.user.pk
    chat_allowed_with_ids = {
        (r if s == uid else s) for s, r in accepted_pair_rows
    }

    from datetime import timedelta
    from django.utils import timezone
    new_threshold = timezone.now() - timedelta(days=7)

    # Preload wishlist matri_ids for current user to mark is_wishlisted flag
    wishlist_matri_ids = set(
        Wishlist.objects.filter(user=request.user)
        .select_related('profile')
        .values_list('profile__matri_id', flat=True)
    )

    profiles_data = []
    for u in page_users:
        pers = getattr(u, 'user_personal', None)
        edu = getattr(u, 'user_education', None)
        photos = getattr(u, 'user_photos', None)
        rel = getattr(u, 'user_religion', None)
        loc = getattr(u, 'user_location', None)

        height_val = height_cm_from_personal(pers)

        photo_url = None
        if photos and photos.profile_photo:
            photo_url = absolute_media_url(request, photos.profile_photo)
        full_photo_url = None
        if photos and photos.full_photo:
            full_photo_url = absolute_media_url(request, photos.full_photo)

        match_pct = int(getattr(u, 'match_score', 0) or 0)
        match_pct = min(100, match_pct)

        last_seen = getattr(u, 'last_seen', None)
        is_online = last_seen and (timezone.now() - last_seen) < timedelta(minutes=15) if last_seen else False

        is_already_viewed = bool(has_plan and getattr(u, 'is_unlocked', False))
        is_able_to_view = bool(has_plan and (is_already_viewed or can_view))

        interest_status, is_interest_sent = interest_ui_by_other_id.get(u.pk, ('pending', False))

        profiles_data.append({
            'matri_id': u.matri_id or '',
            'name': u.name or '',
            'age': age_from_dob(u.dob) if u.dob else None,
            'location': (
                loc.city.name
                if loc and getattr(loc, 'city_id', None) and getattr(loc, 'city', None)
                else (
                    loc.state.name
                    if loc and getattr(loc, 'state_id', None) and getattr(loc, 'state', None)
                    else None
                )
            ),
            'religion': rel.religion.name if rel and rel.religion_id else None,
            'caste': rel.caste_fk.name if rel and rel.caste_fk_id else None,
            'height': height_val,
            'education': edu.highest_education.name if edu and edu.highest_education_id else None,
            'occupation': edu.occupation.name if edu and edu.occupation_id else None,
            'profile_photo': photo_url,
            'full_photo': full_photo_url,
            'is_online': is_online,
            'last_seen': format_last_seen(last_seen) if last_seen else None,
            'is_new': u.created_at >= new_threshold if u.created_at else False,
            'match_percentage': match_pct,
            'is_wishlisted': (u.matri_id in wishlist_matri_ids),
            'is_able_to_view': is_able_to_view,
            'is_already_viewed': is_already_viewed,
            'can_view_details': is_able_to_view,
            'can_send_interest': can_send,
            'can_chat': can_chat_flag and (u.pk in chat_allowed_with_ids),
            'is_interest_sent': is_interest_sent,
            'interest_status': interest_status,
            'is_horoscope_sent': False,
        })

    return Response({
        'success': True,
        'data': {
            'total_profiles': total,
            'page': page,
            'limit': limit,
            'profiles': profiles_data,
        }
    }, status=status.HTTP_200_OK)


class MatchListView(APIView):
    """
    GET /api/v1/matches/
    Query params: page, limit, search, age_min, age_max, height_min, height_max,
    religion_id, caste_id(s), education_id(s), occupation_id(s), marital_status,
    country_id, state_id, district_id(s), city_id(s), profile_with_photo, sort_by.
    caste_ids / education_ids / occupation_ids / district_ids / city_ids accept
    comma-separated lists; repeated singular param names also work.
    When cities are provided they take priority over districts.
    Ordering is by sort_by only (not by ProfileView). Use GET /api/v1/matches/home-slider/ for unviewed-first ordering.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return _match_list_response(request, home_slider=False)


class MatchHomeSliderView(APIView):
    """
    GET /api/v1/matches/home-slider/
    Same filters and response shape as GET /api/v1/matches/, but order is: unviewed first, then viewed, then by created_at
    (sort_by query param is ignored).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return _match_list_response(request, home_slider=True)


class MatchFilterOptionsView(APIView):
    """
    GET /api/v1/matches/filters/
    Returns religions, castes, educations, occupations, marital_status, heights.
    Cached briefly like master lists (invalidated on master writes).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from master import cache_utils as mc
        from master.models import Religion, Caste, Education, Occupation, MaritalStatus, Height

        cached = mc.get_cached_master_list(mc.RESOURCE_MATCH_FILTERS, '')
        if cached is not None:
            return Response(cached)

        religions = list(Religion.objects.filter(is_active=True).order_by('name').values('id', 'name'))
        castes = list(
            Caste.objects.filter(is_active=True).order_by('name').values('id', 'name', 'religion_id')
        )
        educations = list(Education.objects.filter(is_active=True).order_by('name').values('id', 'name'))
        occupations = list(Occupation.objects.filter(is_active=True).order_by('name').values('id', 'name'))
        marital_status = list(
            MaritalStatus.objects.filter(is_active=True).for_display().values('id', 'name')
        )
        heights = list(
            Height.objects.filter(is_active=True).order_by('value_cm').values(
                'id', 'value_cm', 'display_label'
            )
        )
        payload = {
            'success': True,
            'data': {
                'religions': religions,
                'castes': castes,
                'educations': educations,
                'occupations': occupations,
                'marital_status': marital_status,
                'heights': heights,
            },
        }
        mc.set_cached_master_list(mc.RESOURCE_MATCH_FILTERS, '', payload)
        return Response(payload, status=status.HTTP_200_OK)


# Back-compat aliases used by profiles.tests.test_partner_caste_preferences
_apply_partner_preference = apply_partner_preference
_apply_partner_age_preference = apply_partner_age_preference
