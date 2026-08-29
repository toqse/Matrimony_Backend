"""Shared queryset filters for admin / staff / branch profile list endpoints."""
from __future__ import annotations

from datetime import date, datetime

from django.db.models import Q
from django.utils import timezone

from profiles.utils import apply_height_cm_range

from admin_panel.planet_house_filter import (
    PLANET_KEY_TO_INDEX,
    filter_users_by_planet_house,
)
from astrology.porutham import RASI_NAMES

PROFILE_STATUS_FILTERS = frozenset(
    {
        "all",
        "incomplete",
        "complete",
        "subscribed",
        "unsubscribed",
        "verified",
        "unverified",
    }
)

INVALID_PROFILE_STATUS_FILTER_MSG = (
    "Invalid filter. Must be one of: all, incomplete, complete, subscribed, "
    "unsubscribed, verified, unverified."
)


def _qp(request, *keys: str) -> str:
    for key in keys:
        value = (request.query_params.get(key) or "").strip()
        if value:
            return value
    return ""


def _apply_phone_filter(qs, phone: str):
    search_filter = Q(mobile__icontains=phone)
    digits_only = "".join(ch for ch in phone if ch.isdigit())
    if digits_only and digits_only != phone:
        search_filter |= Q(mobile__icontains=digits_only)
    return qs.filter(search_filter)


def _parse_iso_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _horoscope_chart_q():
    """EXE chart string present (11 planet positions)."""
    return Q(horoscope_profile__pr_rasi__isnull=False) & ~Q(horoscope_profile__pr_rasi="")


def _has_horoscope_q():
    return Q(user_profile__has_horoscope=True) | _horoscope_chart_q()


def _active_subscription_q():
    today = timezone.localdate()
    return Q(user_plan__is_active=True) & (
        Q(user_plan__valid_until__isnull=True) | Q(user_plan__valid_until__gte=today)
    )


def _admin_profile_complete_q():
    """Seven-step completion flags on UserProfile (admin list formula)."""
    return Q(
        user_profile__location_completed=True,
        user_profile__religion_completed=True,
        user_profile__personal_completed=True,
        user_profile__family_completed=True,
        user_profile__education_completed=True,
        user_profile__about_completed=True,
        user_profile__photos_completed=True,
    )


def apply_profile_status_filter(qs, filter_value: str):
    """
    Apply profile-status bucket filters (complete, subscribed, verified, etc.).
    Returns (queryset, error_message). error_message is set when filter_value is invalid.
    """
    f = (filter_value or "all").strip().lower()
    if f in {"", "all"}:
        return qs, None
    if f not in PROFILE_STATUS_FILTERS:
        return None, INVALID_PROFILE_STATUS_FILTER_MSG
    if f == "verified":
        return qs.filter(user_profile__admin_verified=True), None
    if f == "unverified":
        return qs.filter(Q(user_profile__isnull=True) | Q(user_profile__admin_verified=False)), None
    if f == "subscribed":
        return qs.filter(_active_subscription_q()), None
    if f == "unsubscribed":
        return qs.exclude(_active_subscription_q()), None
    if f == "complete":
        return qs.filter(_admin_profile_complete_q()), None
    if f == "incomplete":
        return qs.exclude(_admin_profile_complete_q()), None
    return qs, None


def _apply_legacy_search(qs, search: str):
    search_filter = (
        Q(name__icontains=search)
        | Q(matri_id__icontains=search)
        | Q(mobile__icontains=search)
    )
    digits_only = "".join(ch for ch in search if ch.isdigit())
    if digits_only and digits_only != search:
        search_filter |= Q(mobile__icontains=digits_only)
    return qs.filter(search_filter)


def apply_profile_list_filters(qs, request):
    """
    Apply optional query-string filters shared across profile list APIs.

    Supported params:
      matri_id, name, phone|mobile, search (legacy quick search),
      age_from|min_age, age_to|max_age,
      religion_id, caste_id, pr_star|star_id, star (name or number),
      state_id, district_id, education_id, occupation_id, marital_status_id,
      gender, religion_id, plan|plan_id, verified, staff_id, has_photo,
      height_from_cm, height_to_cm, income_id,
      registered_from, registered_to, rasi_id, rasi,
      has_horoscope, planet, planet_house, rajju, dosham,
      filter (profile status buckets — applied separately in views).
      Porutham matching params are handled in profile_porutham_filters.py.
    """
    matri_id = _qp(request, "matri_id")
    if matri_id:
        qs = qs.filter(matri_id__icontains=matri_id)

    name = _qp(request, "name")
    if name:
        qs = qs.filter(name__icontains=name)

    phone = _qp(request, "phone", "mobile", "mobile_number", "phone_number")
    if phone:
        qs = _apply_phone_filter(qs, phone)

    search = _qp(request, "search")
    if search and not (matri_id or name or phone):
        qs = _apply_legacy_search(qs, search)

    today = date.today()
    age_from = _qp(request, "age_from", "min_age")
    if age_from.isdigit():
        max_dob = date(today.year - int(age_from), today.month, today.day)
        qs = qs.filter(dob__isnull=False, dob__lte=max_dob)

    age_to = _qp(request, "age_to", "max_age")
    if age_to.isdigit():
        min_dob = date(today.year - int(age_to) - 1, today.month, today.day)
        qs = qs.filter(dob__isnull=False, dob__gt=min_dob)

    height_from = _qp(request, "height_from_cm", "height_min")
    height_to = _qp(request, "height_to_cm", "height_max")
    qs = apply_height_cm_range(
        qs,
        int(height_from) if height_from.isdigit() else None,
        int(height_to) if height_to.isdigit() else None,
    )

    income_id = _qp(request, "income_id")
    if income_id.isdigit():
        qs = qs.filter(user_education__annual_income_id=int(income_id))

    registered_from = _parse_iso_date(_qp(request, "registered_from"))
    if registered_from:
        qs = qs.filter(created_at__date__gte=registered_from)
    registered_to = _parse_iso_date(_qp(request, "registered_to"))
    if registered_to:
        qs = qs.filter(created_at__date__lte=registered_to)

    religion_id = _qp(request, "religion_id")
    if religion_id.isdigit():
        qs = qs.filter(user_religion__religion_id=int(religion_id))

    caste_id = _qp(request, "caste_id")
    if caste_id.isdigit():
        qs = qs.filter(user_religion__caste_fk_id=int(caste_id))

    state_id = _qp(request, "state_id")
    if state_id.isdigit():
        qs = qs.filter(user_location__district__state_id=int(state_id))

    district_id = _qp(request, "district_id")
    if district_id.isdigit():
        qs = qs.filter(user_location__district_id=int(district_id))

    education_id = _qp(request, "education_id")
    if education_id.isdigit():
        qs = qs.filter(user_education__highest_education_id=int(education_id))

    occupation_id = _qp(request, "occupation_id")
    if occupation_id.isdigit():
        qs = qs.filter(user_education__occupation_id=int(occupation_id))

    marital_status_id = _qp(request, "marital_status_id")
    if marital_status_id.isdigit():
        qs = qs.filter(user_personal__marital_status_id=int(marital_status_id))

    pr_star = _qp(request, "pr_star", "star_id")
    if pr_star.isdigit() and 1 <= int(pr_star) <= 27:
        qs = qs.filter(horoscope_profile__pr_star=int(pr_star))
    else:
        star = _qp(request, "star")
        if star:
            if star.isdigit() and 1 <= int(star) <= 27:
                qs = qs.filter(horoscope_profile__pr_star=int(star))
            else:
                qs = qs.filter(horoscope_profile__star_name__icontains=star)

    rasi_id = _qp(request, "rasi_id")
    if rasi_id.isdigit() and 1 <= int(rasi_id) <= 12:
        rasi_name = RASI_NAMES[int(rasi_id)]
        qs = qs.filter(horoscope_profile__rasi_sign__icontains=rasi_name)
    else:
        rasi = _qp(request, "rasi")
        if rasi:
            qs = qs.filter(horoscope_profile__rasi_sign__icontains=rasi)

    has_horoscope = _qp(request, "has_horoscope").lower()
    if has_horoscope in {"true", "1", "yes"}:
        qs = qs.filter(_has_horoscope_q())
    elif has_horoscope in {"false", "0", "no"}:
        qs = qs.exclude(_has_horoscope_q())

    planet_key = _qp(request, "planet").lower()
    planet_house_raw = _qp(request, "planet_house")
    if (
        planet_key in PLANET_KEY_TO_INDEX
        and planet_house_raw.isdigit()
        and 1 <= int(planet_house_raw) <= 12
    ):
        qs = filter_users_by_planet_house(qs, planet_key, int(planet_house_raw))

    rajju = _qp(request, "rajju")
    if rajju:
        qs = qs.filter(horoscope_profile__rajju__icontains=rajju)

    dosham = _qp(request, "dosham").lower()
    if dosham in {"true", "1", "yes"}:
        qs = qs.exclude(
            Q(user_profile__horoscope_data__dosham__isnull=True)
            | Q(user_profile__horoscope_data__dosham="")
        )
    elif dosham in {"false", "0", "no"}:
        qs = qs.filter(
            Q(user_profile__horoscope_data__dosham__isnull=True)
            | Q(user_profile__horoscope_data__dosham="")
        )

    gender = _qp(request, "gender").upper()
    if gender in {"M", "F", "O"}:
        qs = qs.filter(gender=gender)

    plan = _qp(request, "plan", "plan_id")
    if plan.isdigit():
        qs = qs.filter(user_plan__plan_id=int(plan))
    elif plan:
        qs = qs.filter(user_plan__plan__name__iexact=plan)

    verified = _qp(request, "verified").lower()
    if verified in {"true", "1", "yes"}:
        qs = qs.filter(user_profile__admin_verified=True)
    elif verified in {"false", "0", "no"}:
        qs = qs.filter(Q(user_profile__admin_verified=False) | Q(user_profile__isnull=True))

    staff_id = _qp(request, "staff_id")
    if staff_id.isdigit():
        qs = qs.filter(staff_assignment__staff_id=int(staff_id))

    has_photo = _qp(request, "has_photo").lower()
    if has_photo in {"true", "1", "yes"}:
        qs = qs.filter(user_photos__profile_photo__isnull=False).exclude(user_photos__profile_photo="")
    elif has_photo in {"false", "0", "no"}:
        qs = qs.filter(
            Q(user_photos__isnull=True)
            | Q(user_photos__profile_photo__isnull=True)
            | Q(user_photos__profile_photo="")
        )

    return qs.distinct()
