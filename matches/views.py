"""
Match list API and Filter options API.
"""
from django.db.models import Q
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.models import User
from profiles.models import UserLocation, UserReligion, UserPersonal, UserEducation, UserPhotos
from plans.services import can_view_profile, can_send_interest, can_chat, _get_user_plan
from user_settings.models import UserSettings
from wishlist.models import Wishlist

from .utils import age_from_dob, dob_range_for_age, compute_match_percentage
from .serializers import MatchListProfileSerializer, format_last_seen
from core.media import absolute_media_url


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
    return qs


class MatchListView(APIView):
    """
    GET /api/v1/matches/
    Query params: page, limit, search, age_min, age_max, height_min, height_max,
    religion_id, caste_id, education_id, occupation_id, marital_status, profile_with_photo, sort_by.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = _match_queryset(request)

        # Apply viewer's stored partner religion/caste preference (matches depend on it)
        viewer_rel = UserReligion.objects.filter(user=request.user).first()
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
            # PARTNER_PREFERENCE_ALL: no religion/caste filter from preference
        # Profile visibility: hidden -> exclude; premium_only -> show only to viewers with active plan
        qs = qs.exclude(user_settings__profile_visibility=UserSettings.PROFILE_VISIBILITY_HIDDEN)
        viewer_has_plan = _get_user_plan(request.user) is not None
        if not viewer_has_plan:
            qs = qs.exclude(user_settings__profile_visibility=UserSettings.PROFILE_VISIBILITY_PREMIUM)
        # Query params religion_id/caste_id further narrow (intersection)
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

        # Age filter
        try:
            age_min = int(request.query_params.get('age_min')) if request.query_params.get('age_min') else None
        except (TypeError, ValueError):
            age_min = None
        try:
            age_max = int(request.query_params.get('age_max')) if request.query_params.get('age_max') else None
        except (TypeError, ValueError):
            age_max = None
        if age_min is not None or age_max is not None:
            dob_min, dob_max = dob_range_for_age(age_min, age_max)
            if dob_min is not None:
                qs = qs.filter(dob__gte=dob_min)
            if dob_max is not None:
                qs = qs.filter(dob__lte=dob_max)

        # Height filter (on UserPersonal -> Height.value_cm)
        try:
            height_min = int(request.query_params.get('height_min')) if request.query_params.get('height_min') else None
        except (TypeError, ValueError):
            height_min = None
        try:
            height_max = int(request.query_params.get('height_max')) if request.query_params.get('height_max') else None
        except (TypeError, ValueError):
            height_max = None
        if height_min is not None or height_max is not None:
            qs = qs.filter(user_personal__isnull=False)
        if height_min is not None:
            qs = qs.filter(user_personal__height__value_cm__gte=height_min)
        if height_max is not None:
            qs = qs.filter(user_personal__height__value_cm__lte=height_max)

        # Optional filters
        religion_id = request.query_params.get('religion_id')
        if religion_id:
            try:
                qs = qs.filter(user_religion__religion_id=int(religion_id))
            except (TypeError, ValueError):
                pass
        caste_id = request.query_params.get('caste_id')
        if caste_id:
            try:
                qs = qs.filter(user_religion__caste_fk_id=int(caste_id))
            except (TypeError, ValueError):
                pass
        education_id = request.query_params.get('education_id')
        if education_id:
            try:
                qs = qs.filter(user_education__highest_education_id=int(education_id))
            except (TypeError, ValueError):
                pass
        occupation_id = request.query_params.get('occupation_id')
        if occupation_id:
            try:
                qs = qs.filter(user_education__occupation_id=int(occupation_id))
            except (TypeError, ValueError):
                pass
        marital_status = request.query_params.get('marital_status')
        if marital_status:
            try:
                qs = qs.filter(user_personal__marital_status_id=int(marital_status))
            except (TypeError, ValueError):
                pass

        # Only with profile photo
        if request.query_params.get('profile_with_photo') in ('1', 'true', 'yes'):
            qs = qs.filter(user_photos__profile_photo__isnull=False)

        qs = qs.distinct()

        # Sort
        sort_by = request.query_params.get('sort_by', 'newest')
        if sort_by == 'newest':
            qs = qs.order_by('-created_at')
        else:
            qs = qs.order_by('-created_at')

        # Pagination
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            limit = max(1, min(50, int(request.query_params.get('limit', 10))))
        except (TypeError, ValueError):
            limit = 10
        total = qs.count()
        start = (page - 1) * limit
        qs = qs.select_related(
            'user_personal', 'user_personal__height', 'user_personal__marital_status',
            'user_religion', 'user_religion__religion', 'user_religion__caste_fk',
            'user_education', 'user_education__highest_education', 'user_education__occupation',
            'user_photos', 'user_location',
        ).distinct()[start:start + limit]

        # Plan permissions for viewer
        can_view, _ = can_view_profile(request.user)
        can_send, _ = can_send_interest(request.user)
        can_chat_flag, _ = can_chat(request.user)

        # Load viewer's profile for match %
        viewer = request.user
        viewer_rel = getattr(viewer, 'user_religion', None) or UserReligion.objects.filter(user=viewer).select_related('religion', 'caste_fk').first()
        viewer_pers = getattr(viewer, 'user_personal', None) or UserPersonal.objects.filter(user=viewer).select_related('height', 'marital_status').first()
        viewer_edu = getattr(viewer, 'user_education', None) or UserEducation.objects.filter(user=viewer).select_related('highest_education', 'occupation').first()
        viewer_loc = getattr(viewer, 'user_location', None) or UserLocation.objects.filter(user=viewer).select_related('state', 'city').first()

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
        for u in qs:
            pers = getattr(u, 'user_personal', None)
            edu = getattr(u, 'user_education', None)
            photos = getattr(u, 'user_photos', None)
            rel = getattr(u, 'user_religion', None)
            loc = getattr(u, 'user_location', None)

            height_val = None
            if pers and pers.height_id and getattr(pers, 'height', None):
                height_val = pers.height.value_cm
            elif pers and getattr(pers, 'height_text', None) and str(pers.height_text).replace(' ', '').isdigit():
                try:
                    height_val = int(str(pers.height_text).replace(' ', ''))
                except ValueError:
                    pass

            photo_url = None
            if photos and photos.profile_photo:
                photo_url = absolute_media_url(request, photos.profile_photo)

            match_pct = compute_match_percentage(
                viewer, u,
                viewer_rel, viewer_pers, viewer_edu, viewer_loc,
                rel, pers, edu, loc
            )

            last_seen = getattr(u, 'last_seen', None)
            is_online = last_seen and (timezone.now() - last_seen) < timedelta(minutes=15) if last_seen else False

            profiles_data.append({
                'matri_id': u.matri_id or '',
                'name': u.name or '',
                'age': age_from_dob(u.dob) if u.dob else None,
                'height': height_val,
                'education': edu.highest_education.name if edu and edu.highest_education_id else None,
                'occupation': edu.occupation.name if edu and edu.occupation_id else None,
                'profile_photo': photo_url,
                'is_online': is_online,
                'last_seen': format_last_seen(last_seen) if last_seen else None,
                'is_new': u.created_at >= new_threshold if u.created_at else False,
                'match_percentage': match_pct,
                'is_wishlisted': (u.matri_id in wishlist_matri_ids),
                'can_view_details': can_view,
                'can_send_interest': can_send,
                'can_chat': can_chat_flag,
            })

        # Re-sort by match_percentage if sort_by is best_match or most_relevant
        if sort_by in ('best_match', 'most_relevant'):
            profiles_data.sort(key=lambda x: x['match_percentage'] or 0, reverse=True)

        return Response({
            'success': True,
            'data': {
                'total_profiles': total,
                'page': page,
                'limit': limit,
                'profiles': profiles_data,
            }
        }, status=status.HTTP_200_OK)


class MatchFilterOptionsView(APIView):
    """
    GET /api/v1/matches/filters/
    Returns religions, castes, educations, occupations, marital_status, heights.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from master.models import Religion, Caste, Education, Occupation, MaritalStatus, Height
        religions = list(Religion.objects.filter(is_active=True).order_by('name').values('id', 'name'))
        castes = list(Caste.objects.filter(is_active=True).select_related('religion').order_by('name').values('id', 'name', 'religion_id'))
        educations = list(Education.objects.filter(is_active=True).order_by('name').values('id', 'name'))
        occupations = list(Occupation.objects.filter(is_active=True).order_by('name').values('id', 'name'))
        marital_status = list(MaritalStatus.objects.filter(is_active=True).order_by('name').values('id', 'name'))
        heights = list(Height.objects.filter(is_active=True).order_by('value_cm').values('id', 'value_cm', 'display_label'))
        return Response({
            'success': True,
            'data': {
                'religions': religions,
                'castes': castes,
                'educations': educations,
                'occupations': occupations,
                'marital_status': marital_status,
                'heights': heights,
            }
        }, status=status.HTTP_200_OK)
