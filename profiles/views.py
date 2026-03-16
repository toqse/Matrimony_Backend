"""
Profile completion APIs: location, religion, personal, education, about, photos, complete.
GET/PATCH profile section APIs and base GET /profile/ for full profile.
"""
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser

from .models import (
    UserProfile, UserLocation, UserReligion, UserPersonal,
    UserFamily, UserEducation, UserPhotos,
)
from .utils import mark_profile_step_completed, generate_about_me, generate_about_me_suggestions
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
)


class ProfileDetailView(APIView):
    """GET /api/v1/profile/ - complete profile grouped by sections."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
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
        data = {
            'id': str(user.pk),
            'matri_id': user.matri_id or '',
            'basic_details': basic_ser.data,
            'photos': PhotosDetailsReadSerializer(photos).data if photos else _empty_photos(),
            'religion_details': ReligionDetailsReadSerializer(rel).data if rel else {},
            'personal_details': PersonalDetailsReadSerializer(pers).data if pers else {},
            'location_details': LocationDetailsReadSerializer(loc).data if loc else {},
            'family_details': FamilyDetailsReadSerializer(fam).data if fam else {},
            'education_details': EducationDetailsReadSerializer(edu).data if edu else {},
            'about_me': profile.about_me if profile else '',
        }
        return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)


def _build_profile_data_for_user(user, include_contact=False, include_family=True):
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
    basic_data = basic_ser.data
    if not include_contact:
        basic_data = {k: v for k, v in basic_data.items() if k not in ('email', 'phone', 'phone_number')}

    data = {
        'id': str(user.pk),
        'matri_id': user.matri_id or '',
        'basic_details': basic_data,
        'photos': PhotosDetailsReadSerializer(photos).data if photos else _empty_photos(),
        'religion_details': ReligionDetailsReadSerializer(rel).data if rel else {},
        'personal_details': PersonalDetailsReadSerializer(pers).data if pers else {},
        'location_details': LocationDetailsReadSerializer(loc).data if loc else {},
        'education_details': EducationDetailsReadSerializer(edu).data if edu else {},
        'about_me': profile.about_me if profile else '',
    }
    if include_family:
        data['family_details'] = FamilyDetailsReadSerializer(fam).data if fam else {}
    else:
        data['family_details'] = {}
    return data


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
        from plans.services import can_view_contact

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

        # Reuse existing helper to gather profile data without contact details.
        profile = _build_profile_data_for_user(profile_user, include_contact=False, include_family=True)
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
        if city and state:
            location_str = f'{city}, {state}'
        else:
            location_str = city or state or None

        height_val = personal.get('height_cm')
        height_str = None
        if isinstance(height_val, (int, float)):
            height_str = f'{height_val} cm'
        elif isinstance(height_val, str):
            height_str = height_val

        mother_tongue = religion.get('mother_tongue')
        profile_photo = photos.get('profile_photo')

        about_me = profile.get('about_me') or ''
        family_background = family.get('about_family') or ''

        can_view_contact_flag, _ = can_view_contact(viewer)

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
            'about_me': about_me,
            'family_background': family_background,
            'contact_locked': not can_view_contact_flag,
        }

        return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)


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

        if can_view:
            # Full profile; decrement and record view
            data = _build_profile_data_for_user(profile_user, include_contact=True, include_family=True)
            ProfileViewModel.objects.create(viewer=viewer, viewed_user=profile_user)
            PlanLimitService.consume_profile_view(viewer)
            # Refresh plan_block after decrement
            plan_info = get_plan_info_for_response(viewer)
            plan_block['profile_views_remaining'] = plan_info.get('profile_views_remaining')
        else:
            # Limited profile: no contact, no family
            data = _build_profile_data_for_user(profile_user, include_contact=False, include_family=False)

        return Response({
            'success': True,
            'data': {
                'profile': data,
                'plan': plan_block,
            }
        }, status=status.HTTP_200_OK)


class BasicDetailsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ser = BasicDetailsReadSerializer(request.user)
        return Response({'success': True, 'data': ser.data}, status=status.HTTP_200_OK)

    def patch(self, request):
        ser = BasicDetailsUpdateSerializer(request.user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
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
        return Response({'success': True, 'data': out_ser.data}, status=status.HTTP_200_OK)

    def post(self, request):
        ser = UserLocationSerializer(data=request.data, context={'request': request})
        ser.is_valid(raise_exception=True)
        ser.create(ser.validated_data)
        mark_profile_step_completed(request.user, 'location')
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
        ser = ReligionDetailsUpdateSerializer(data=request.data, partial=True)
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
        if 'partner_caste_preference' in ser.validated_data:
            defaults['partner_caste_preference'] = ser.validated_data['partner_caste_preference']
        UserReligion.objects.update_or_create(user=request.user, defaults=defaults)
        mark_profile_step_completed(request.user, 'religion')
        rel = UserReligion.objects.filter(user=request.user).select_related(
            'religion', 'caste_fk', 'mother_tongue'
        ).first()
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
                'partner_caste_preference': UserReligion.PARTNER_CASTE_ANY,
            }
            return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)
        data = PartnerPreferencesReadSerializer(rel).data
        return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)

    def patch(self, request):
        ser = PartnerPreferencesUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        rel, _ = UserReligion.objects.get_or_create(user=request.user, defaults={})
        for key in ('partner_preference_type', 'partner_religion_ids', 'partner_caste_preference'):
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
        if ser.validated_data.get('marital_status_id') is not None:
            pers.marital_status_id = ser.validated_data['marital_status_id']
        if 'number_of_children' in ser.validated_data:
            pers.number_of_children = ser.validated_data['number_of_children']
        if ser.validated_data.get('height_cm') is not None:
            pers.height_text = f"{ser.validated_data['height_cm']} cm"
        if ser.validated_data.get('weight_kg') is not None:
            pers.weight = ser.validated_data['weight_kg']
        if 'colour' in ser.validated_data:
            pers.colour = ser.validated_data['colour']
        if 'blood_group' in ser.validated_data:
            pers.blood_group = ser.validated_data['blood_group']
        pers.save()
        mark_profile_step_completed(request.user, 'personal')
        pers = UserPersonal.objects.filter(user=request.user).select_related('marital_status', 'height').first()
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
        fam = UserFamily.objects.filter(user=request.user).first()
        if not fam:
            return Response({'success': True, 'data': {}}, status=status.HTTP_200_OK)
        return Response({'success': True, 'data': FamilyDetailsReadSerializer(fam).data}, status=status.HTTP_200_OK)

    def patch(self, request):
        ser = FamilyDetailsUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        fam, _ = UserFamily.objects.get_or_create(user=request.user, defaults={})
        for k in ser.validated_data:
            setattr(fam, k, ser.validated_data[k])
        fam.save()
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
        ser = EducationDetailsUpdateSerializer(data=request.data, partial=True)
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

    def get(self, request):
        photos = UserPhotos.objects.filter(user=request.user).first()
        if not photos:
            return Response({'success': True, 'data': {}}, status=status.HTTP_200_OK)
        return Response({
            'success': True,
            'data': PhotosDetailsReadSerializer(photos).data,
        }, status=status.HTTP_200_OK)

    def patch(self, request):
        photos, _ = UserPhotos.objects.get_or_create(user=request.user, defaults={})
        ser = UserPhotosSerializer(photos, data=request.data, partial=True, context={'request': request})
        ser.is_valid(raise_exception=True)
        ser.save()
        mark_profile_step_completed(request.user, 'photos')
        return Response({
            'success': True,
            'data': PhotosDetailsReadSerializer(ser.instance).data,
        }, status=status.HTTP_200_OK)

    def post(self, request):
        ser = UserPhotosSerializer(data=request.data, context={'request': request}, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        mark_profile_step_completed(request.user, 'photos')
        return Response({'success': True, 'message': 'Photos saved.'}, status=status.HTTP_200_OK)


class ProfileCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        user.is_registration_profile_completed = True
        user.save(update_fields=['is_registration_profile_completed', 'updated_at'])
        return Response({
            'success': True,
            'message': 'Profile marked as complete.',
            'data': {'is_registration_profile_completed': True},
        }, status=status.HTTP_200_OK)


# Need to fix serializers: UserLocationSerializer has no save() - we have create(). So in the view we call ser.save() but Serializer with only create() requires ser.save() to call create(). So we need to not pass instance. So ser.save() will call create(validated_data). Good. But we didn't define save() - the base Serializer.save() calls self.create(self.validated_data). So we're good. Let me double-check: Base Serializer.save() does: return self.create(self.validated_data). So we need to return the object from create(). We do. So the view should not expect ser.save() to return something we use - we just need no exception. So we're good. But UserLocationSerializer.create() returns obj - and we're not using it in the view. Good.