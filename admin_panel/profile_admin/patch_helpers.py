"""Apply admin PATCH payloads to a target user (same rules as user-facing profile APIs)."""
from profiles.models import (
    UserEducation,
    UserFamily,
    UserLocation,
    UserPersonal,
    UserProfile,
    UserReligion,
)
from profiles.serializers import (
    AboutDetailsUpdateSerializer,
    BasicDetailsUpdateSerializer,
    EducationDetailsUpdateSerializer,
    FamilyDetailsUpdateSerializer,
    LocationDetailsUpdateSerializer,
    PersonalDetailsUpdateSerializer,
    ReligionDetailsUpdateSerializer,
)
from profiles.utils import sync_profile_completion_flags


def apply_basic_details(user, payload: dict):
    ser = BasicDetailsUpdateSerializer(user, data=payload, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()


def apply_location(user, payload: dict):
    ser = LocationDetailsUpdateSerializer(data=payload, partial=True)
    ser.is_valid(raise_exception=True)
    vd = ser.validated_data
    defaults = {"address": vd.get("address", "")}
    for k in ("country_id", "state_id", "district_id", "city_id"):
        if vd.get(k) is not None:
            defaults[k] = vd[k]
    UserLocation.objects.update_or_create(user=user, defaults=defaults)
    sync_profile_completion_flags(user)


def apply_religion(user, payload: dict):
    class _DummyReq:
        def __init__(self, req_user):
            self.user = req_user

    ser = ReligionDetailsUpdateSerializer(
        data=payload,
        partial=True,
        context={'request': _DummyReq(user)},
    )
    ser.is_valid(raise_exception=True)
    vd = ser.validated_data
    defaults = {"partner_religion_preference": vd.get("partner_religion_preference", "")}
    if vd.get("religion_id") is not None:
        defaults["religion_id"] = vd["religion_id"]
    if vd.get("caste_id") is not None:
        defaults["caste_fk_id"] = vd["caste_id"]
    if vd.get("mother_tongue_id") is not None:
        defaults["mother_tongue_id"] = vd["mother_tongue_id"]
    if "partner_preference_type" in vd:
        defaults["partner_preference_type"] = vd["partner_preference_type"]
    if "partner_religion_ids" in vd:
        defaults["partner_religion_ids"] = vd["partner_religion_ids"]
    if "partner_caste_preferences" in vd:
        defaults["partner_caste_preferences"] = vd["partner_caste_preferences"]
    UserReligion.objects.update_or_create(user=user, defaults=defaults)
    sync_profile_completion_flags(user)


def apply_personal(user, payload: dict):
    ser = PersonalDetailsUpdateSerializer(data=payload, partial=True)
    ser.is_valid(raise_exception=True)
    pers, _ = UserPersonal.objects.get_or_create(user=user, defaults={})
    vd = ser.validated_data
    if vd.get("marital_status") is not None:
        pers.marital_status_id = vd["marital_status"]
    if "has_children" in vd:
        pers.has_children = vd["has_children"]
        if vd["has_children"] is False and "number_of_children" not in vd:
            pers.number_of_children = 0
    if "number_of_children" in vd:
        pers.number_of_children = vd["number_of_children"] if vd["number_of_children"] is not None else 0
    height_val = vd.get("height_cm")
    if height_val is None and vd.get("height") is not None:
        height_val = vd["height"]
    if height_val is not None:
        pers.height_text = f"{height_val} cm"
    weight_val = vd.get("weight_kg")
    if weight_val is None and vd.get("weight") is not None:
        weight_val = vd["weight"]
    if weight_val is not None:
        pers.weight = weight_val
    if "complexion" in vd:
        pers.colour = vd["complexion"] or ""
    if "colour" in vd:
        pers.colour = vd["colour"]
    if "blood_group" in vd:
        pers.blood_group = vd["blood_group"]
    pers.save()
    sync_profile_completion_flags(user)


def apply_family(user, payload: dict):
    ser = FamilyDetailsUpdateSerializer(data=payload, partial=True)
    ser.is_valid(raise_exception=True)
    fam, _ = UserFamily.objects.get_or_create(user=user, defaults={})
    for k in ser.validated_data:
        setattr(fam, k, ser.validated_data[k])
    fam.save()
    sync_profile_completion_flags(user)


def apply_education(user, payload: dict):
    ser = EducationDetailsUpdateSerializer(
        data=payload, partial=True, context={'user': user}
    )
    ser.is_valid(raise_exception=True)
    vd = ser.validated_data
    edu, _ = UserEducation.objects.get_or_create(user=user, defaults={})
    if vd.get("highest_education_id") is not None:
        edu.highest_education_id = vd["highest_education_id"]
    if vd.get("education_subject_id") is not None:
        edu.education_subject_id = vd["education_subject_id"]
    if "employment_status" in vd:
        edu.employment_status = vd["employment_status"]
    if vd.get("occupation_id") is not None:
        edu.occupation_id = vd["occupation_id"]
    if vd.get("annual_income_id") is not None:
        edu.annual_income_id = vd["annual_income_id"]
    edu.save()
    sync_profile_completion_flags(user)


def apply_about(user, payload: dict):
    if not isinstance(payload, dict):
        payload = {"about_me": payload}
    ser = AboutDetailsUpdateSerializer(data=payload, partial=True)
    ser.is_valid(raise_exception=True)
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={})
    if "about_me" in ser.validated_data:
        profile.about_me = ser.validated_data["about_me"]
    profile.save(update_fields=["about_me", "updated_at"])
    sync_profile_completion_flags(user)


SECTION_HANDLERS = {
    "basic_details": apply_basic_details,
    "location_details": apply_location,
    "religion_details": apply_religion,
    "personal_details": apply_personal,
    "family_details": apply_family,
    "education_details": apply_education,
    "about_me": apply_about,
}
