"""
Profile completion APIs: location, religion, personal, education, about, photos, complete.
GET/PATCH profile section APIs and base GET /profile/ for full profile.
"""
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.media import absolute_media_url
from .models import (
    UserProfile, UserLocation, UserReligion, UserPersonal,
    UserFamily, UserEducation, UserPhotos,
)
from .utils import (
    mark_profile_step_completed,
    generate_about_me,
    generate_about_me_suggestions,
    get_profile_completion_data,
    is_profile_registration_complete,
    is_profile_visible_to_others,
)
from .serializers import (
    UserLocationSerializer,
    UserReligionSerializer,
    UserPersonalSerializer,
    UserEducationSerializer,
    UserProfileAboutSerializer,
    UserPhotosSerializer,
    BasicDetailsReadSerializer,
    BasicDetailsUpdateSerializer,
    ReligionDetailsReadSerializer,
    ReligionDetailsUpdateSerializer,
    PartnerPreferencesReadSerializer,
    PartnerPreferencesUpdateSerializer,
    PersonalDetailsReadSerializer,
    PersonalDetailsUpdateSerializer,
    LocationDetailsReadSerializer,
    LocationDetailsUpdateSerializer,
    FamilyDetailsReadSerializer,
    FamilyDetailsUpdateSerializer,
    EducationDetailsReadSerializer,
    EducationDetailsUpdateSerializer,
    PhotosDetailsReadSerializer,
    AboutDetailsUpdateSerializer,
    BirthDetailsUpdateSerializer,
    empty_education_details_read_data,
    empty_family_details_read_data,
    empty_location_details_read_data,
    empty_personal_details_read_data,
    empty_religion_details_read_data,
)
from admin_panel.audit_log.models import AuditLog
from admin_panel.audit_log.utils import create_audit_log


def _audit_member_profile(request, details: str, *, action: str | None = None) -> None:
    # Staff/Branch-manager only logs: member profile self-updates should not create audit rows.
    return


def _build_profile_data_for_user(user, request=None, include_contact=False, include_family=True):
    """Build profile dict for a given user (for public profile view)."""
    from .serializers import (
        BasicDetailsReadSerializer, ReligionDetailsReadSerializer,
        PersonalDetailsReadSerializer, LocationDetailsReadSerializer,
        FamilyDetailsReadSerializer, EducationDetailsReadSerializer,
        PhotosDetailsReadSerializer,
    )
    loc = UserLocation.objects.filter(user=user).select_related('country', 'state', 'district', 'city').first()
    rel = UserReligion.objects.filter(user=user).select_related('religion', 'caste_fk', 'mother_tongue').first()
    pers = UserPersonal.objects.filter(user=user).select_related('marital_status', 'height').first()
    fam = UserFamily.objects.filter(user=user).first()
    edu = UserEducation.objects.filter(user=user).select_related(
        'highest_education', 'education_subject', 'occupation', 'annual_income'
    ).first()
    photos = UserPhotos.objects.filter(user=user).first()
    profile = getattr(user, 'user_profile', None) or UserProfile.objects.filter(user=user).first()

    def _empty_photos():
        return {
            'profile_photo': None, 'full_photo': None, 'selfie_photo': None, 'family_photo': None,
            'aadhaar_front': None, 'aadhaar_back': None,
        }

    basic_ser = BasicDetailsReadSerializer(user)
    basic_data = dict(basic_ser.data)
    if not include_contact:
        basic_data['email'] = None
        basic_data['phone'] = None

    data = {
        'id': str(user.pk),
        'matri_id': user.matri_id or '',
        'basic_details': basic_data,
        'photos': PhotosDetailsReadSerializer(photos, context={'request': request}).data if photos else _empty_photos(),
        'religion_details': ReligionDetailsReadSerializer(rel).data if rel else empty_religion_details_read_data(),
        'personal_details': PersonalDetailsReadSerializer(pers).data if pers else empty_personal_details_read_data(),
        'location_details': LocationDetailsReadSerializer(loc).data if loc else empty_location_details_read_data(),
        'education_details': EducationDetailsReadSerializer(edu).data if edu else empty_education_details_read_data(),
        'about_me': profile.about_me if profile else '',
    }
    if include_family:
        data['family_details'] = FamilyDetailsReadSerializer(fam).data if fam else empty_family_details_read_data()
    else:
        data['family_details'] = empty_family_details_read_data()
    return data


class ProfileDetailView(APIView):
    """GET /api/v1/profile/ - complete profile grouped by sections."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        completion = get_profile_completion_data(user)
        data = _build_profile_data_for_user(user, request, include_contact=True, include_family=True)
        data['profile_completion_percentage'] = completion['profile_completion_percentage']
        return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)


class ProfilePreviewByMatriIdView(APIView):
    """
    GET /api/v1/profiles/{matri_id}/preview/
    Lightweight profile preview for popup on matches page.
    Does NOT decrement profile view limits or create ProfileView records.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, matri_id):
        from accounts.models import User
        from matches.utils import age_from_dob
        from plans.services import (
            can_view_contact,
            can_view_profile,
            can_send_interest,
            can_chat,
            get_interest_ui_state_for_viewer,
            has_accepted_interest_between,
        )
        from plans.models import ProfileView as ProfileViewModel
        from wishlist.models import Wishlist

        viewer = request.user
        try:
            profile_user = User.objects.get(matri_id=matri_id, is_active=True)
        except User.DoesNotExist:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'Profile not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        if profile_user.pk == viewer.pk:
            return Response(
                {'success': False, 'error': {'code': 400, 'message': 'Cannot view own profile here.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not is_profile_visible_to_others(profile_user):
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'Profile not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        target_up = UserProfile.objects.filter(user=profile_user).first()
        is_viewed_by_me = (
            ProfileViewModel.objects.filter(viewer=viewer, profile=target_up).exists()
            if target_up
            else False
        )
        interest_status, is_interest_sent = get_interest_ui_state_for_viewer(viewer, profile_user)
        is_wishlisted = Wishlist.objects.filter(user=viewer, profile=profile_user).exists()

        # Reuse existing helper to gather profile data without contact details.
        profile = _build_profile_data_for_user(profile_user, request=request, include_contact=False, include_family=True)
        basic = profile.get('basic_details') or {}
        personal = profile.get('personal_details') or {}
        location = profile.get('location_details') or {}
        religion = profile.get('religion_details') or {}
        education = profile.get('education_details') or {}
        family = profile.get('family_details') or {}
        photos = profile.get('photos') or {}

        # Derive simple fields for popup.
        age = age_from_dob(profile_user.dob) if getattr(profile_user, 'dob', None) else None

        city = location.get('city')
        state = location.get('state')
        # Preview card expects the location field to carry city first.
        # Keep state as a fallback when city is not available.
        location_str = city or state or None

        height_val = personal.get('height_cm')
        height_str = None
        if isinstance(height_val, (int, float)):
            height_str = f'{height_val} cm'
        elif isinstance(height_val, str):
            height_str = height_val

        mother_tongue = religion.get('mother_tongue')
        profile_photo = photos.get('profile_photo')
        full_photo = photos.get('full_photo')

        about_me = profile.get('about_me') or ''
        family_background = family.get('about_family') or ''

        can_view_contact_flag, _ = can_view_contact(viewer)
        can_view_flag, _ = can_view_profile(viewer)
        can_send_interest_flag, _ = can_send_interest(viewer)
        can_chat_flag, _ = can_chat(viewer)
        can_chat_effective = bool(
            can_chat_flag and has_accepted_interest_between(viewer, profile_user)
        )
        is_able_to_view = bool(is_viewed_by_me or can_view_flag)
        opposite_profile = getattr(profile_user, 'user_profile', None)
        can_horoscope_match = bool(
            getattr(profile_user, 'dob', None)
            and opposite_profile
            and getattr(opposite_profile, 'time_of_birth', None)
            and (getattr(opposite_profile, 'place_of_birth', '') or '').strip()
        )

        data = {
            'matri_id': profile_user.matri_id or '',
            'name': basic.get('name') or profile_user.name or '',
            'age': age,
            'location': location_str,
            'religion': religion.get('religion'),
            'caste': religion.get('caste'),
            'education': education.get('highest_education'),
            'occupation': education.get('occupation'),
            'annual_income': education.get('annual_income'),
            'marital_status': personal.get('marital_status'),
            'height': height_str,
            'mother_tongue': mother_tongue,
            'profile_photo': profile_photo,
            'full_photo': full_photo,
            'about_me': about_me,
            'family_background': family_background,
            'contact_locked': not can_view_contact_flag,
            'is_wishlisted': is_wishlisted,
            'is_able_to_view': is_able_to_view,
            'is_already_viewed': is_viewed_by_me,
            'can_view_details': is_able_to_view,
            'can_send_interest': can_send_interest_flag,
            'can_chat': can_chat_effective,
            'is_interest_sent': is_interest_sent,
            'interest_status': interest_status,
            'is_horoscope_sent': False,
            'can_horoscope_match': can_horoscope_match,
        }

        out = {'success': True, 'data': {**data, 'is_viewed_by_me': is_viewed_by_me}}

        # If the viewer already unlocked this profile via a prior full-view,
        # include full details here too (without consuming profile view credits again).
        if is_viewed_by_me:
            out['data']['profile'] = _build_profile_data_for_user(
                profile_user, request=request, include_contact=True, include_family=True
            )

        return Response(
            out,
            status=status.HTTP_200_OK,
        )


class PublicProfileByMatriIdView(APIView):
    """
    GET /api/v1/profiles/{matri_id}/
    View another user's profile. If plan allows and limit remaining: full profile and decrement view count.
    If limit exceeded: restricted profile (no contact, no family). Response always includes plan info for UI.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, matri_id):
        from accounts.models import User
        from plans.services import PlanLimitService, get_plan_info_for_response
        from plans.models import ProfileView as ProfileViewModel
        from django.db import transaction

        viewer = request.user
        try:
            profile_user = User.objects.get(matri_id=matri_id, is_active=True)
        except User.DoesNotExist:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'Profile not found.'}},
                status=status.HTTP_404_NOT_FOUND
            )
        if profile_user.pk == viewer.pk:
            return Response(
                {'success': False, 'error': {'code': 400, 'message': 'Cannot view own profile here.'}},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not is_profile_visible_to_others(profile_user):
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'Profile not found.'}},
                status=status.HTTP_404_NOT_FOUND
            )

        target_up = UserProfile.objects.filter(user=profile_user).first()
        already_viewed = (
            ProfileViewModel.objects.filter(viewer=viewer, profile=target_up).exists()
            if target_up
            else False
        )
        can_view, remaining = PlanLimitService.can_view_profile(viewer)
        plan_info = get_plan_info_for_response(viewer)
        # Build plan block for "view details" UI so frontend can display plan
        plan_block = {
            'name': plan_info.get('plan_name'),
            'valid_until': plan_info.get('valid_until'),
            'profile_views_remaining': plan_info.get('profile_views_remaining'),
            'interests_remaining': plan_info.get('interests_remaining'),
            'chat_remaining': plan_info.get('chat_remaining'),
        }

        if already_viewed:
            # Already unlocked earlier; do not decrement again. Bump last_viewed_at for home-slider ordering.
            data = _build_profile_data_for_user(profile_user, request=request, include_contact=True, include_family=True)
            if target_up:
                ProfileViewModel.objects.filter(viewer=viewer, profile=target_up).update(
                    last_viewed_at=timezone.now()
                )
        elif can_view:
            # First-time full view: record view and consume once. touch() updates last_viewed_at on every repeat.
            data = _build_profile_data_for_user(profile_user, request=request, include_contact=True, include_family=True)
            with transaction.atomic():
                if target_up:
                    _, created = ProfileViewModel.touch(viewer, target_up)
                    if created:
                        PlanLimitService.consume_profile_view(viewer)
            # Refresh plan_block after potential decrement
            plan_info = get_plan_info_for_response(viewer)
            plan_block['profile_views_remaining'] = plan_info.get('profile_views_remaining')
        else:
            # Limited profile: no contact, no family
            data = _build_profile_data_for_user(profile_user, request=request, include_contact=False, include_family=False)

        return Response({
            'success': True,
            'data': {
                'profile': data,
                'plan': plan_block,
            }
        }, status=status.HTTP_200_OK)


class ProfileViewRecordView(APIView):
    """
    POST /api/v1/profiles/{matri_id}/view/
    Idempotently records that the logged-in user viewed this profile (match ordering & analytics).
    Call as many times as needed for the same matri_id; each call updates last_viewed_at for home-slider reordering.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, matri_id):
        from accounts.models import User
        from plans.models import ProfileView

        try:
            profile_user = User.objects.get(matri_id=matri_id, is_active=True)
        except User.DoesNotExist:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'Profile not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if profile_user.pk == request.user.pk:
            return Response(
                {'success': False, 'error': {'code': 400, 'message': 'Cannot view own profile.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not is_profile_visible_to_others(profile_user):
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'Profile not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        up = UserProfile.objects.filter(user=profile_user).first()
        if not up:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'Profile not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            ProfileView.touch(request.user, up)
        except IntegrityError:
            ProfileView.objects.filter(viewer=request.user, profile=up).update(
                last_viewed_at=timezone.now()
            )
        return Response({'success': True}, status=status.HTTP_200_OK)


class ProfileCompletionView(APIView):
    """
    GET /api/v1/profile/completion/
    Returns completion percentage and steps remaining for dashboard quick actions.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        completion = get_profile_completion_data(request.user)
        steps_remaining = []
        step_labels = {
            'location': 'Add location',
            'religion': 'Add religion',
            'personal': 'Add personal details',
            'family': 'Add family details',
            'education': 'Add education',
            'about': 'Add about me',
            'photos': 'Upload photos',
        }
        for step in ('location', 'religion', 'personal', 'family', 'education', 'about', 'photos'):
            if not completion['profile_steps'].get(step, False):
                steps_remaining.append(step_labels.get(step, step))
        rel = UserReligion.objects.filter(user=request.user).first()
        if not rel or (getattr(rel, 'partner_preference_type', None) or '') == '':
            if 'Add partner preference' not in steps_remaining:
                steps_remaining.append('Add partner preference')
        return Response({
            'success': True,
            'data': {
                'completion_percentage': completion['profile_completion_percentage'],
                'steps_remaining': steps_remaining,
            },
        }, status=status.HTTP_200_OK)


class ProfileRegistrationCompletedView(APIView):
    """
    GET /api/v1/profile/registration-completed/
    Returns whether all registration steps (profile sections + partner preference) are done.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'success': True,
            'data': {
                'is_profile_completed': is_profile_registration_complete(request.user),
            },
        }, status=status.HTTP_200_OK)


class ProfileViewsView(APIView):
    """
    GET /api/v1/profile/views/
    Returns total profile views count.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from plans.models import ProfileView
        total = ProfileView.objects.filter(profile__user=request.user).count()
        return Response({
            'success': True,
            'data': {'total_views': total},
        }, status=status.HTTP_200_OK)


class BasicDetailsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        ser = BasicDetailsReadSerializer(user)
        data = dict(ser.data)
        photos = UserPhotos.objects.filter(user=user).first()
        loc = UserLocation.objects.filter(user=user).select_related('state', 'city').first()
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
        data['profile_photo'] = profile_photo
        data['location'] = location_str or ''
        data['matri_id'] = user.matri_id or ''
        return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)

    def patch(self, request):
        ser = BasicDetailsUpdateSerializer(request.user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        try:
            ser.save()
        except IntegrityError:
            raise ValidationError({'email': ['Email already exists. Please use a different email.']})
        _audit_member_profile(request, "Basic details updated.")
        return Response({'success': True, 'data': BasicDetailsReadSerializer(ser.instance).data}, status=status.HTTP_200_OK)


class ProfileLocationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        loc = UserLocation.objects.filter(user=request.user).select_related(
            'country', 'state', 'district', 'city'
        ).first()
        if not loc:
            return Response({'success': True, 'data': {}}, status=status.HTTP_200_OK)
        ser = LocationDetailsReadSerializer(loc)
        return Response({'success': True, 'data': ser.data}, status=status.HTTP_200_OK)

    def patch(self, request):
        ser = LocationDetailsUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        defaults = {'address': ser.validated_data.get('address', '')}
        for k in ('country_id', 'state_id', 'district_id', 'city_id'):
            if ser.validated_data.get(k) is not None:
                defaults[k] = ser.validated_data[k]
        loc, _ = UserLocation.objects.update_or_create(user=request.user, defaults=defaults)
        out_ser = LocationDetailsReadSerializer(
            UserLocation.objects.filter(user=request.user).select_related(
                'country', 'state', 'district', 'city'
            ).first()
        )
        _audit_member_profile(request, "Location details updated.")
        return Response({'success': True, 'data': out_ser.data}, status=status.HTTP_200_OK)

    def post(self, request):
        ser = UserLocationSerializer(data=request.data, context={'request': request})
        ser.is_valid(raise_exception=True)
        ser.create(ser.validated_data)
        mark_profile_step_completed(request.user, 'location')
        _audit_member_profile(request, "Location details created.")
        return Response({'success': True, 'message': 'Location saved.'}, status=status.HTTP_200_OK)


class ProfileReligionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rel = UserReligion.objects.filter(user=request.user).select_related(
            'religion', 'caste_fk', 'mother_tongue'
        ).first()
        if not rel:
            return Response({'success': True, 'data': {}}, status=status.HTTP_200_OK)
        return Response({'success': True, 'data': ReligionDetailsReadSerializer(rel).data}, status=status.HTTP_200_OK)

    def patch(self, request):
        ser = ReligionDetailsUpdateSerializer(data=request.data, partial=True, context={'request': request})
        ser.is_valid(raise_exception=True)
        defaults = {'partner_religion_preference': ser.validated_data.get('partner_religion_preference', '')}
        if ser.validated_data.get('religion_id') is not None:
            defaults['religion_id'] = ser.validated_data['religion_id']
        if ser.validated_data.get('caste_id') is not None:
            defaults['caste_fk_id'] = ser.validated_data['caste_id']
        if ser.validated_data.get('mother_tongue_id') is not None:
            defaults['mother_tongue_id'] = ser.validated_data['mother_tongue_id']
        if 'partner_preference_type' in ser.validated_data:
            defaults['partner_preference_type'] = ser.validated_data['partner_preference_type']
        if 'partner_religion_ids' in ser.validated_data:
            defaults['partner_religion_ids'] = ser.validated_data['partner_religion_ids']
        if 'partner_caste_preferences' in ser.validated_data:
            defaults['partner_caste_preferences'] = ser.validated_data['partner_caste_preferences']
        UserReligion.objects.update_or_create(user=request.user, defaults=defaults)
        mark_profile_step_completed(request.user, 'religion')
        rel = UserReligion.objects.filter(user=request.user).select_related(
            'religion', 'caste_fk', 'mother_tongue'
        ).first()
        _audit_member_profile(request, "Religion details updated.")
        return Response({
            'success': True,
            'data': ReligionDetailsReadSerializer(rel).data if rel else {},
        }, status=status.HTTP_200_OK)

    def post(self, request):
        ser = UserReligionSerializer(data=request.data, context={'request': request})
        ser.is_valid(raise_exception=True)
        ser.create(ser.validated_data)
        mark_profile_step_completed(request.user, 'religion')
        return Response({'success': True, 'message': 'Religion saved.'}, status=status.HTTP_200_OK)


class PartnerPreferencesView(APIView):
    """GET/PATCH /api/v1/profile/partner-preferences/ – structured partner religion/caste preference."""
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def get(self, request):
        rel = UserReligion.objects.filter(user=request.user).first()
        if not rel:
            data = {
                'partner_preference_type': UserReligion.PARTNER_PREFERENCE_ALL,
                'partner_religion_ids': [],
                'partner_caste_preferences': {},
            }
            return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)
        data = PartnerPreferencesReadSerializer(rel).data
        return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)

    def patch(self, request):
        return self._update_preferences(request)

    def post(self, request):
        """POST for quick action 'Set Partner Preferences' - same as PATCH."""
        return self._update_preferences(request)

    def _update_preferences(self, request):
        rel, _ = UserReligion.objects.get_or_create(user=request.user, defaults={})
        ser = PartnerPreferencesUpdateSerializer(
            data=request.data,
            partial=True,
            context={'request': request, 'existing_obj': rel, 'user': request.user},
        )
        ser.is_valid(raise_exception=True)
        for key in ('partner_preference_type', 'partner_religion_ids', 'partner_caste_preferences'):
            if key in ser.validated_data:
                setattr(rel, key, ser.validated_data[key])
        rel.save()
        return Response({
            'success': True,
            'data': PartnerPreferencesReadSerializer(rel).data,
        }, status=status.HTTP_200_OK)


class ProfilePersonalView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        pers = UserPersonal.objects.filter(user=request.user).select_related('marital_status', 'height').first()
        if not pers:
            return Response({'success': True, 'data': {}}, status=status.HTTP_200_OK)
        return Response({'success': True, 'data': PersonalDetailsReadSerializer(pers).data}, status=status.HTTP_200_OK)

    def patch(self, request):
        ser = PersonalDetailsUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        pers, _ = UserPersonal.objects.get_or_create(user=request.user, defaults={})
        if ser.validated_data.get('marital_status') is not None:
            pers.marital_status_id = ser.validated_data['marital_status']
        if 'has_children' in ser.validated_data:
            pers.has_children = ser.validated_data['has_children']
            if ser.validated_data['has_children'] is False and 'number_of_children' not in ser.validated_data:
                pers.number_of_children = 0
        if 'number_of_children' in ser.validated_data:
            pers.number_of_children = ser.validated_data['number_of_children'] if ser.validated_data['number_of_children'] is not None else 0
        height_val = ser.validated_data.get('height_cm')
        if height_val is None and ser.validated_data.get('height') is not None:
            height_val = ser.validated_data['height']
        if height_val is not None:
            pers.height_text = f"{height_val} cm"
        weight_val = ser.validated_data.get('weight_kg')
        if weight_val is None and ser.validated_data.get('weight') is not None:
            weight_val = ser.validated_data['weight']
        if weight_val is not None:
            pers.weight = weight_val
        if 'complexion' in ser.validated_data:
            pers.colour = ser.validated_data['complexion'] or ''
        if 'colour' in ser.validated_data:
            pers.colour = ser.validated_data['colour']
        if 'blood_group' in ser.validated_data:
            pers.blood_group = ser.validated_data['blood_group']
        pers.save()
        mark_profile_step_completed(request.user, 'personal')
        pers = UserPersonal.objects.filter(user=request.user).select_related('marital_status', 'height').first()
        _audit_member_profile(request, "Personal details updated.")
        return Response({'success': True, 'data': PersonalDetailsReadSerializer(pers).data}, status=status.HTTP_200_OK)

    def post(self, request):
        ser = UserPersonalSerializer(data=request.data, context={'request': request})
        ser.is_valid(raise_exception=True)
        ser.create(ser.validated_data)
        mark_profile_step_completed(request.user, 'personal')
        return Response({'success': True, 'message': 'Personal details saved successfully.'}, status=status.HTTP_200_OK)


class ProfileFamilyView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]  # Family details are JSON only; avoid multipart parse errors

    def get(self, request):
        from .serializers import empty_family_details_read_data

        fam = UserFamily.objects.filter(user=request.user).first()
        if not fam:
            return Response({'success': True, 'data': empty_family_details_read_data()}, status=status.HTTP_200_OK)
        return Response({'success': True, 'data': FamilyDetailsReadSerializer(fam).data}, status=status.HTTP_200_OK)

    def patch(self, request):
        ser = FamilyDetailsUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        fam, _ = UserFamily.objects.get_or_create(user=request.user, defaults={})
        for k in ser.validated_data:
            setattr(fam, k, ser.validated_data[k])
        fam.save()
        mark_profile_step_completed(request.user, 'family')
        _audit_member_profile(request, "Family details updated.")
        return Response({'success': True, 'data': FamilyDetailsReadSerializer(fam).data}, status=status.HTTP_200_OK)


class ProfileEducationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        edu = UserEducation.objects.filter(user=request.user).select_related(
            'highest_education', 'education_subject', 'occupation', 'annual_income'
        ).first()
        if not edu:
            return Response({'success': True, 'data': {}}, status=status.HTTP_200_OK)
        return Response({'success': True, 'data': EducationDetailsReadSerializer(edu).data}, status=status.HTTP_200_OK)

    def patch(self, request):
        ser = EducationDetailsUpdateSerializer(
            data=request.data, partial=True, context={'request': request}
        )
        ser.is_valid(raise_exception=True)
        edu, _ = UserEducation.objects.get_or_create(user=request.user, defaults={})
        if ser.validated_data.get('highest_education_id') is not None:
            edu.highest_education_id = ser.validated_data['highest_education_id']
        if ser.validated_data.get('education_subject_id') is not None:
            edu.education_subject_id = ser.validated_data['education_subject_id']
        if 'employment_status' in ser.validated_data:
            edu.employment_status = ser.validated_data['employment_status']
        if ser.validated_data.get('occupation_id') is not None:
            edu.occupation_id = ser.validated_data['occupation_id']
        if ser.validated_data.get('annual_income_id') is not None:
            edu.annual_income_id = ser.validated_data['annual_income_id']
        edu.save()
        mark_profile_step_completed(request.user, 'education')
        edu = UserEducation.objects.filter(user=request.user).select_related(
            'highest_education', 'education_subject', 'occupation', 'annual_income'
        ).first()
        _audit_member_profile(request, "Education details updated.")
        return Response({'success': True, 'data': EducationDetailsReadSerializer(edu).data}, status=status.HTTP_200_OK)

    def post(self, request):
        ser = UserEducationSerializer(data=request.data, context={'request': request})
        ser.is_valid(raise_exception=True)
        ser.create(ser.validated_data)
        mark_profile_step_completed(request.user, 'education')
        return Response({'success': True, 'message': 'Education saved.'}, status=status.HTTP_200_OK)


class ProfileGenerateAboutView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        about_me = generate_about_me(user)
        suggestions = generate_about_me_suggestions(user)
        return Response({
            'success': True,
            'data': {
                'about_me': about_me,
                'suggestions': suggestions,
            },
        }, status=status.HTTP_200_OK)


class ProfileAboutView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = UserProfile.objects.filter(user=request.user).first()
        about_me = profile.about_me if profile else ''
        return Response({'success': True, 'data': {'about_me': about_me}}, status=status.HTTP_200_OK)

    def patch(self, request):
        ser = AboutDetailsUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        profile, _ = UserProfile.objects.get_or_create(user=request.user, defaults={})
        if 'about_me' in ser.validated_data:
            profile.about_me = ser.validated_data['about_me']
        profile.save()
        mark_profile_step_completed(request.user, 'about')
        _audit_member_profile(request, "About me updated.")
        return Response({'success': True, 'data': {'about_me': profile.about_me}}, status=status.HTTP_200_OK)

    def post(self, request):
        ser = UserProfileAboutSerializer(data=request.data, context={'request': request})
        ser.is_valid(raise_exception=True)
        ser.create(ser.validated_data)
        mark_profile_step_completed(request.user, 'about')
        return Response({'success': True, 'message': 'About me saved.'}, status=status.HTTP_200_OK)


class ProfilePhotosView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    PHOTO_FIELD_MAP = {
        1: 'profile_photo',
        2: 'full_photo',
        3: 'selfie_photo',
        4: 'family_photo',
        5: 'aadhaar_front',
        6: 'aadhaar_back',
    }

    def get(self, request):
        photos = UserPhotos.objects.filter(user=request.user).first()
        if not photos:
            return Response({'success': True, 'data': {}}, status=status.HTTP_200_OK)
        return Response({
            'success': True,
            'data': PhotosDetailsReadSerializer(photos, context={'request': request}).data,
        }, status=status.HTTP_200_OK)

    def patch(self, request):
        photos, _ = UserPhotos.objects.get_or_create(user=request.user, defaults={})
        ser = UserPhotosSerializer(photos, data=request.data, partial=True, context={'request': request})
        ser.is_valid(raise_exception=True)
        ser.save()
        mark_profile_step_completed(request.user, 'photos')
        _audit_member_profile(request, "Photos updated.")
        return Response({
            'success': True,
            'data': PhotosDetailsReadSerializer(ser.instance, context={'request': request}).data,
        }, status=status.HTTP_200_OK)

    def post(self, request):
        ser = UserPhotosSerializer(data=request.data, context={'request': request}, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        mark_profile_step_completed(request.user, 'photos')
        return Response({'success': True, 'message': 'Photos saved.'}, status=status.HTTP_200_OK)

    def delete(self, request, photo_id):
        field_name = self.PHOTO_FIELD_MAP.get(photo_id)
        if not field_name:
            return Response(
                {
                    'success': False,
                    'error': {
                        'code': 400,
                        'message': 'Invalid photo_id. Use 1=profile_photo, 2=full_photo, 3=selfie_photo, 4=family_photo, 5=aadhaar_front, 6=aadhaar_back.',
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        photos = UserPhotos.objects.filter(user=request.user).first()
        if not photos:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'No photos found for this user.'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        image_field = getattr(photos, field_name, None)
        if not image_field:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': f'No image found for photo_id {photo_id}.'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        image_field.delete(save=False)
        setattr(photos, field_name, None)
        photos.save()
        _audit_member_profile(request, f"Photo deleted: {field_name}.", action=AuditLog.ACTION_DELETE)

        return Response(
            {
                'success': True,
                'message': f'Photo deleted for photo_id {photo_id}.',
                'data': PhotosDetailsReadSerializer(photos, context={'request': request}).data,
            },
            status=status.HTTP_200_OK,
        )


class ProfileCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        user.is_registration_profile_completed = True
        user.save(update_fields=['is_registration_profile_completed', 'updated_at'])
        _audit_member_profile(request, "Profile marked complete.")
        return Response({
            'success': True,
            'message': 'Profile marked as complete.',
            'data': {'is_registration_profile_completed': True},
        }, status=status.HTTP_200_OK)


class ProfileBirthDetailsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = UserProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response({'success': True, 'data': {}}, status=status.HTTP_200_OK)
        data = {
            'time_of_birth': profile.time_of_birth,
            'place_of_birth': profile.place_of_birth,
        }
        return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = BirthDetailsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile, _ = UserProfile.objects.get_or_create(user=request.user, defaults={})
        profile.time_of_birth = serializer.validated_data['time_of_birth']
        profile.place_of_birth = serializer.validated_data['place_of_birth']
        profile.save(update_fields=['time_of_birth', 'place_of_birth', 'updated_at'])
        _audit_member_profile(request, "Birth details updated.")
        return Response({
            'success': True,
            'message': 'Birth details updated successfully.',
            'data': {
                'time_of_birth': profile.time_of_birth,
                'place_of_birth': profile.place_of_birth,
            },
        }, status=status.HTTP_200_OK)


# Need to fix serializers: UserLocationSerializer has no save() - we have create(). So in the view we call ser.save() but Serializer with only create() requires ser.save() to call create(). So we need to not pass instance. So ser.save() will call create(validated_data). Good. But we didn't define save() - the base Serializer.save() calls self.create(self.validated_data). So we're good. Let me double-check: Base Serializer.save() does: return self.create(self.validated_data). So we need to return the object from create(). We do. So the view should not expect ser.save() to return something we use - we just need no exception. So we're good. But UserLocationSerializer.create() returns obj - and we're not using it in the view. Good.