"""
Profile completion helpers: step tracking, percentage, next step, status.
About Me generator: professional matrimony-style paragraph from profile data.
"""
import math
from django.db.models import IntegerField, Value
from django.db.models.functions import Cast, Coalesce
from .models import (
    UserProfile, UserLocation, UserReligion, UserPersonal,
    UserFamily, UserEducation, UserPhotos,
)

# Ordered profile steps (used for next_step and consistent response)
PROFILE_STEP_ORDER = (
    'location',
    'religion',
    'personal',
    'family',
    'education',
    'about',
    'photos',
)

# Visibility threshold: 6/7 completed steps -> int(85.71) == 85
PROFILE_VISIBILITY_MIN_PERCENTAGE = 85


def _family_completion_ratio(user):
    """
    Return family step completion as a value between 0.0 and 1.0.
    Uses field-level completion so percentage grows/drops proportionally.
    """
    fam = UserFamily.objects.filter(user=user).first()
    if not fam:
        return 0.0

    # Keep this aligned with editable family text fields to avoid counting
    # model defaults (e.g. numeric 0) as completed input.
    tracked_fields = (
        'father_name',
        'father_occupation',
        'mother_name',
        'mother_occupation',
        'about_family',
        'family_type',
        'family_status',
    )
    filled = 0
    for field in tracked_fields:
        value = getattr(fam, field, '')
        if isinstance(value, str) and value.strip():
            filled += 1

    return filled / len(tracked_fields)


def _compute_step_completion(user):
    """Compute step completion from actual section data."""
    loc = UserLocation.objects.filter(user=user).first()
    rel = UserReligion.objects.filter(user=user).first()
    pers = UserPersonal.objects.filter(user=user).first()
    fam = UserFamily.objects.filter(user=user).first()
    edu = UserEducation.objects.filter(user=user).first()
    photos = UserPhotos.objects.filter(user=user).first()
    profile = UserProfile.objects.filter(user=user).first()

    family_ratio = _family_completion_ratio(user)
    location_completed = bool(
        loc and (
            loc.country_id
            or loc.state_id
            or loc.district_id
            or loc.city_id
            or (loc.address or '').strip()
        )
    )
    religion_completed = bool(
        rel and (
            rel.religion_id
            or rel.caste_fk_id
            or (rel.caste or '').strip()
            or rel.mother_tongue_id
            or (rel.gothram or '').strip()
        )
    )
    personal_completed = bool(
        pers and (
            pers.marital_status_id
            or pers.height_id
            or (pers.height_text or '').strip()
            or pers.weight is not None
            or (pers.colour or '').strip()
            or (pers.blood_group or '').strip()
            or pers.has_children
            or (pers.number_of_children or 0) > 0
            or (pers.children_living_with or '').strip()
        )
    )
    family_completed = family_ratio >= 1.0
    education_completed = bool(
        edu and (
            edu.highest_education_id
            or edu.education_subject_id
            or edu.occupation_id
            or edu.annual_income_id
            or (edu.employment_status or '').strip()
            or (edu.company or '').strip()
            or (edu.working_location or '').strip()
        )
    )
    about_completed = bool(profile and (profile.about_me or '').strip())
    photos_completed = bool(
        photos and (
            photos.profile_photo
            or photos.full_photo
            or photos.selfie_photo
            or photos.family_photo
            or photos.aadhaar_front
            or photos.aadhaar_back
            or (photos.profile_photo_url or '').strip()
        )
    )

    return {
        'location': location_completed,
        'religion': religion_completed,
        'personal': personal_completed,
        'family': family_completed,
        'education': education_completed,
        'about': about_completed,
        'photos': photos_completed,
        'family_ratio': family_ratio,
    }


def sync_profile_completion_flags(user):
    """Persist step flags on UserProfile based on actual profile data."""
    defaults = {
        'location_completed': False,
        'religion_completed': False,
        'personal_completed': False,
        'family_completed': False,
        'education_completed': False,
        'about_completed': False,
        'photos_completed': False,
    }
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults=defaults)
    steps = _compute_step_completion(user)
    updates = {}
    mapping = {
        'location': 'location_completed',
        'religion': 'religion_completed',
        'personal': 'personal_completed',
        'family': 'family_completed',
        'education': 'education_completed',
        'about': 'about_completed',
        'photos': 'photos_completed',
    }
    for step_key, field in mapping.items():
        value = bool(steps[step_key])
        if getattr(profile, field) != value:
            setattr(profile, field, value)
            updates[field] = value
    if updates:
        profile.save(update_fields=[*updates.keys(), 'updated_at'])
    return steps


def get_profile_completion_data(user):
    """
    Build profile completion payload for API responses.

    Ensures UserProfile exists for the user. Returns dict with:
    - profile_steps: { step_name: bool, ... }
    - profile_completion_percentage: int 0-100
    - next_step: first incomplete step name or None if all complete
    - profile_status: "completed" | "incomplete"
    """
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            'location_completed': False,
            'religion_completed': False,
            'personal_completed': False,
            'family_completed': False,
            'education_completed': False,
            'about_completed': False,
            'photos_completed': False,
        },
    )
    steps = sync_profile_completion_flags(user)
    family_ratio = steps['family_ratio']
    profile_steps = {
        'location': bool(steps['location']),
        'religion': bool(steps['religion']),
        'personal': bool(steps['personal']),
        'family': bool(steps['family']),
        'education': bool(steps['education']),
        'about': bool(steps['about']),
        'photos': bool(steps['photos']),
    }
    completed_non_family_steps = sum(
        value for key, value in profile_steps.items() if key != 'family'
    )
    total_steps = len(profile_steps)
    profile_completion_percentage = int(
        ((completed_non_family_steps + family_ratio) / total_steps) * 100
    ) if total_steps else 0

    next_step = None
    for step in PROFILE_STEP_ORDER:
        if not profile_steps[step]:
            next_step = step
            break

    profile_status = 'completed' if profile_completion_percentage == 100 else 'incomplete'

    return {
        'profile_steps': profile_steps,
        'profile_completion_percentage': profile_completion_percentage,
        'next_step': next_step,
        'profile_status': profile_status,
    }


def is_profile_registration_complete(user):
    """
    True when registration is effectively complete for onboarding:
    - all profile steps are complete, OR
    - completion is >= 85 and the only pending profile step is "family".
    In both cases, partner_preference_type must be set on UserReligion.
    """
    completion = get_profile_completion_data(user)
    profile_steps = completion['profile_steps']
    pending_steps = [step for step in PROFILE_STEP_ORDER if not profile_steps.get(step, False)]
    is_full_complete = len(pending_steps) == 0
    is_family_only_pending = (
        completion['profile_completion_percentage'] >= PROFILE_VISIBILITY_MIN_PERCENTAGE
        and pending_steps == ['family']
    )
    if not (is_full_complete or is_family_only_pending):
        return False
    rel = UserReligion.objects.filter(user=user).first()
    if not rel or (getattr(rel, 'partner_preference_type', None) or '') == '':
        return False
    return True


def is_profile_visible_to_others(user):
    """
    Profile should be discoverable only after reaching minimum completion threshold.
    """
    completion = get_profile_completion_data(user)
    return completion['profile_completion_percentage'] >= PROFILE_VISIBILITY_MIN_PERCENTAGE


def filter_visible_profiles_queryset(queryset):
    """
    Query-safe visibility filter using normalized profile completion flags.
    Keeps match/dashboard visibility criteria aligned in one place.
    """
    completion_score = (
        Coalesce(Cast('user_profile__location_completed', IntegerField()), Value(0))
        + Coalesce(Cast('user_profile__religion_completed', IntegerField()), Value(0))
        + Coalesce(Cast('user_profile__personal_completed', IntegerField()), Value(0))
        + Coalesce(Cast('user_profile__family_completed', IntegerField()), Value(0))
        + Coalesce(Cast('user_profile__education_completed', IntegerField()), Value(0))
        + Coalesce(Cast('user_profile__about_completed', IntegerField()), Value(0))
        + Coalesce(Cast('user_profile__photos_completed', IntegerField()), Value(0))
    )
    min_steps = math.ceil((PROFILE_VISIBILITY_MIN_PERCENTAGE / 100) * len(PROFILE_STEP_ORDER))
    return queryset.annotate(profile_completion_steps=completion_score).filter(profile_completion_steps__gte=min_steps)


def get_full_profile_data(user, request=None):
    """
    Build the full profile dict for a user (same structure as GET /api/v1/profile/).
    Used e.g. in verify-OTP response to return all previously saved profile data.
    """
    from .serializers import (
        BasicDetailsReadSerializer,
        PhotosDetailsReadSerializer,
        ReligionDetailsReadSerializer,
        PersonalDetailsReadSerializer,
        LocationDetailsReadSerializer,
        FamilyDetailsReadSerializer,
        EducationDetailsReadSerializer,
        empty_education_details_read_data,
        empty_family_details_read_data,
        empty_location_details_read_data,
        empty_personal_details_read_data,
        empty_religion_details_read_data,
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
    return {
        'id': str(user.pk),
        'matri_id': user.matri_id or '',
        'basic_details': basic_ser.data,
        'photos': PhotosDetailsReadSerializer(photos, context={'request': request}).data if photos else _empty_photos(),
        'religion_details': ReligionDetailsReadSerializer(rel).data if rel else empty_religion_details_read_data(),
        'personal_details': PersonalDetailsReadSerializer(pers).data if pers else empty_personal_details_read_data(),
        'location_details': LocationDetailsReadSerializer(loc).data if loc else empty_location_details_read_data(),
        'family_details': FamilyDetailsReadSerializer(fam).data if fam else empty_family_details_read_data(),
        'education_details': EducationDetailsReadSerializer(edu).data if edu else empty_education_details_read_data(),
        'about_me': profile.about_me if profile else '',
    }


def mark_profile_step_completed(user, step):
    """
    Mark a profile step as completed for the user.
    step: one of 'location', 'religion', 'personal', 'family', 'education', 'about', 'photos'
    """
    step_to_field = {
        'location': 'location_completed',
        'religion': 'religion_completed',
        'personal': 'personal_completed',
        'family': 'family_completed',
        'education': 'education_completed',
        'about': 'about_completed',
        'photos': 'photos_completed',
    }
    field = step_to_field.get(step)
    if not field:
        return
    defaults = {
        'location_completed': False,
        'religion_completed': False,
        'personal_completed': False,
        'family_completed': False,
        'education_completed': False,
        'about_completed': False,
        'photos_completed': False,
    }
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults=defaults)
    if not getattr(profile, field):
        setattr(profile, field, True)
        profile.save(update_fields=[field, 'updated_at'])


def _get_profile_context(user):
    """Gather location, religion, personal, education for the user. Returns a simple namespace-like dict."""
    loc = UserLocation.objects.filter(user=user).select_related('city', 'state').first()
    rel = UserReligion.objects.filter(user=user).select_related('religion', 'mother_tongue').first()
    pers = UserPersonal.objects.filter(user=user).select_related('marital_status', 'height').first()
    edu = UserEducation.objects.filter(user=user).select_related(
        'highest_education', 'occupation'
    ).first()
    return {
        'city': loc.city.name if loc and loc.city else None,
        'state': loc.state.name if loc and loc.state else None,
        'religion': rel.religion if rel else None,
        'mother_tongue': rel.mother_tongue if rel else None,
        'marital_status': pers.marital_status if pers else None,
        'height_text': pers.height_text if pers else '',
        'height_fk': pers.height if pers else None,
        'education': edu.highest_education if edu else None,
        'occupation': edu.occupation if edu else None,
    }


def generate_about_me(user):
    """
    Build a professional matrimony-style 'About Me' paragraph from the user's profile.
    Skips missing fields gracefully. Uses friendly relationship wording.
    """
    ctx = _get_profile_context(user)
    parts = []

    if ctx['city'] and ctx['state']:
        parts.append(
            f"I am a family-oriented person currently based in {ctx['city']}, {ctx['state']}."
        )
    elif ctx['city']:
        parts.append(f"I am a family-oriented person currently based in {ctx['city']}.")
    elif ctx['state']:
        parts.append(f"I am a family-oriented person currently based in {ctx['state']}.")

    if ctx['education']:
        parts.append(f"I have completed my {ctx['education'].name}.")

    if ctx['occupation']:
        parts.append(f"I work as a {ctx['occupation'].name}.")

    if ctx['religion']:
        parts.append(f"I belong to a {ctx['religion'].name} family.")

    if ctx['mother_tongue']:
        parts.append(f"My mother tongue is {ctx['mother_tongue'].name}.")

    if ctx['marital_status']:
        parts.append(f"I am {ctx['marital_status'].name}.")

    height_str = ctx['height_text']
    if not height_str and ctx['height_fk']:
        height_str = ctx['height_fk'].display_label or (
            f"{ctx['height_fk'].value_cm} cm" if ctx['height_fk'].value_cm else None
        )
    if height_str:
        parts.append(f"My height is {height_str}.")

    parts.append(
        "I value honesty and strong family relationships and look forward to finding a caring life partner."
    )

    return " ".join(parts) if parts else "Complete your profile to generate About Me."


def generate_about_me_suggestions(user):
    """
    Return three paragraph variations for better UX (main + two alternatives).
    """
    main = generate_about_me(user)
    ctx = _get_profile_context(user)
    suggestions = [main]

    # Variation 2: lead with education/career if present
    parts2 = []
    if ctx['education']:
        parts2.append(f"I have completed my {ctx['education'].name}.")
    if ctx['occupation']:
        parts2.append(f"I work as a {ctx['occupation'].name}.")
    if ctx['city'] and ctx['state']:
        parts2.append(f"I am currently based in {ctx['city']}, {ctx['state']}.")
    elif ctx['city']:
        parts2.append(f"I am currently based in {ctx['city']}.")
    if ctx['religion']:
        parts2.append(f"I belong to a {ctx['religion'].name} family.")
    if ctx['mother_tongue']:
        parts2.append(f"My mother tongue is {ctx['mother_tongue'].name}.")
    parts2.append(
        "I value honesty and strong family relationships and look forward to finding a caring life partner."
    )
    if parts2:
        suggestions.append(" ".join(parts2))

    # Variation 3: lead with family/values
    parts3 = []
    if ctx['city'] and ctx['state']:
        parts3.append(f"Based in {ctx['city']}, {ctx['state']}, I am a family-oriented person.")
    if ctx['religion']:
        parts3.append(f"I belong to a {ctx['religion'].name} family.")
    if ctx['mother_tongue']:
        parts3.append(f"My mother tongue is {ctx['mother_tongue'].name}.")
    if ctx['education'] and ctx['occupation']:
        parts3.append(f"I have completed my {ctx['education'].name} and work as a {ctx['occupation'].name}.")
    elif ctx['education']:
        parts3.append(f"I have completed my {ctx['education'].name}.")
    elif ctx['occupation']:
        parts3.append(f"I work as a {ctx['occupation'].name}.")
    parts3.append(
        "I value honesty and strong family relationships and look forward to finding a caring life partner."
    )
    if parts3:
        suggestions.append(" ".join(parts3))

    return suggestions[:3]
