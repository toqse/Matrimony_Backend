"""
Profile completion helpers: step tracking, percentage, next step, status.
About Me generator: professional matrimony-style paragraph from profile data.
"""
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
    profile_steps = {
        'location': profile.location_completed,
        'religion': profile.religion_completed,
        'personal': profile.personal_completed,
        'family': getattr(profile, 'family_completed', False),
        'education': profile.education_completed,
        'about': profile.about_completed,
        'photos': profile.photos_completed,
    }
    completed_steps = sum(profile_steps.values())
    total_steps = len(profile_steps)
    profile_completion_percentage = int((completed_steps / total_steps) * 100) if total_steps else 0

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


def is_profile_visible_to_others(user):
    """
    Profile should be discoverable only after reaching minimum completion threshold.
    """
    completion = get_profile_completion_data(user)
    return completion['profile_completion_percentage'] >= PROFILE_VISIBILITY_MIN_PERCENTAGE


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
        'religion_details': ReligionDetailsReadSerializer(rel).data if rel else {},
        'personal_details': PersonalDetailsReadSerializer(pers).data if pers else {},
        'location_details': LocationDetailsReadSerializer(loc).data if loc else {},
        'family_details': FamilyDetailsReadSerializer(fam).data if fam else {},
        'education_details': EducationDetailsReadSerializer(edu).data if edu else {},
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
