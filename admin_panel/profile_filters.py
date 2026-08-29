"""Shared queryset filters for admin / staff / branch profile list endpoints."""
from __future__ import annotations

from datetime import date, datetime

from django.db.models import CharField, Q, TextField
from django.db.models.functions import Length, Lower, Substr, Upper
from django.utils import timezone

from profiles.utils import apply_height_cm_range

from admin_panel.planet_house_filter import (
    PLANET_KEY_TO_INDEX,
    filter_users_by_planet_house,
)
from astrology.porutham import RASI_NAMES, STAR_NAMES, bride_chovva, chart_to_array, groom_chovva

CharField.register_lookup(Lower)
TextField.register_lookup(Lower)

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


def _ci_contains(field: str, value: str) -> Q:
    """Case-insensitive substring match via LOWER(), portable across DB engines."""
    needle = (value or "").casefold()
    if not needle:
        return Q()
    return Q(**{f"{field}__lower__contains": needle})


def _ci_exact(field: str, value: str) -> Q:
    """Case-insensitive exact match via LOWER(), portable across DB engines."""
    needle = (value or "").casefold()
    if not needle:
        return Q()
    return Q(**{f"{field}__lower": needle})


def _apply_phone_filter(qs, phone: str):
    search_filter = _ci_contains("mobile", phone)
    digits_only = "".join(ch for ch in phone if ch.isdigit())
    if digits_only and digits_only != phone:
        search_filter |= _ci_contains("mobile", digits_only)
    return qs.filter(search_filter)


def _parse_iso_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


# Same Padam/Kanda/Udara mapping used when derived rajju is filled from pr_star.
_STAR_RAJJU = (
    "",
    "Padam", "Padam", "Padam", "Padam", "Padam", "Padam",
    "Kanda", "Kanda", "Kanda", "Kanda", "Kanda", "Kanda",
    "Udara", "Udara", "Udara", "Udara", "Udara", "Udara",
    "Kanda", "Kanda", "Kanda", "Kanda", "Kanda", "Kanda",
    "Padam", "Padam", "Padam",
)

_RAJJU_ALIAS_GROUPS = (
    frozenset({"padam", "pada"}),
    frozenset({"kanda", "kanta", "kati"}),
    frozenset({"udara", "nabhi"}),
    frozenset({"siro", "sira", "siras"}),
)

_DOSHAM_FALSE_VALUES = frozenset({"", "no", "false", "0", "none", "nil", "n", "na"})


def _apply_has_horoscope_filter(qs, raw: str):
    """Check horoscope = ready 11-char pr_rasi, not the registration checkbox."""
    raw = (raw or "").lower()
    qs = qs.alias(_chart_len=Length("horoscope_profile__pr_rasi"))
    ready = Q(_chart_len__gte=11)
    not_ready = Q(_chart_len__isnull=True) | Q(_chart_len__lt=11)
    if raw in {"true", "1", "yes"}:
        return qs.filter(ready)
    if raw in {"false", "0", "no"}:
        return qs.filter(not_ready)
    return qs


def _star_match_q(star_num: int) -> Q:
    q = Q(horoscope_profile__pr_star=star_num)
    if 1 <= star_num < len(STAR_NAMES) and STAR_NAMES[star_num]:
        q |= _ci_contains("horoscope_profile__star_name", STAR_NAMES[star_num])
    return q


def _rasi_id_from_name(name: str) -> int | None:
    needle = (name or "").casefold().strip()
    if not needle:
        return None
    for idx, rasi_name in enumerate(RASI_NAMES):
        if idx and rasi_name.casefold() == needle:
            return idx
    return None


def _apply_rasi_id_filter(qs, rasi_id: int):
    """Match stored rasi_sign or moon sign from pr_rasi (Chandran, 3rd character)."""
    rasi_name = RASI_NAMES[rasi_id]
    letter = chr(ord("A") + rasi_id - 1)
    qs = qs.alias(_moon_l=Upper(Substr("horoscope_profile__pr_rasi", 3, 1)))
    return qs.filter(
        _ci_contains("horoscope_profile__rasi_sign", rasi_name) | Q(_moon_l=letter)
    )


def _rajju_names(label: str) -> set[str]:
    needle = (label or "").casefold().strip()
    if not needle:
        return set()
    for group in _RAJJU_ALIAS_GROUPS:
        if needle in group:
            return set(group)
    return {needle}


def _rajju_q(label: str) -> Q:
    names = _rajju_names(label)
    q = Q()
    for name in names:
        q |= _ci_contains("horoscope_profile__rajju", name)
    star_ids = [
        idx for idx, value in enumerate(_STAR_RAJJU) if value and value.casefold() in names
    ]
    if star_ids:
        q |= Q(horoscope_profile__pr_star__in=star_ids)
    return q


def _truthy_dosham(value) -> bool:
    if value is True or value == 1:
        return True
    if value is False or value is None or value == 0:
        return False
    text = str(value).strip().casefold()
    if text in _DOSHAM_FALSE_VALUES:
        return False
    return bool(text)


def _chart_has_chovva(pr_rasi: str | None, gender: str | None) -> bool:
    if not pr_rasi or len(pr_rasi) < 11:
        return False
    arr = chart_to_array(pr_rasi)
    if not arr:
        return False
    g = (gender or "").upper()
    if g == "F":
        return bool(bride_chovva(arr))
    if g == "M":
        return bool(groom_chovva(arr))
    return bool(bride_chovva(arr) or groom_chovva(arr))


def _filter_users_by_dosham(qs, want_yes: bool):
    """Yes = stored horoscope_data.dosham or Kuja/chovva on the rasi chart."""
    from accounts.models import User
    from astrology.models import HoroscopeProfile
    from profiles.models import UserProfile

    yes_ids: set = set()
    scoped = qs.values("pk")

    for profile in UserProfile.objects.filter(user_id__in=scoped).only("user_id", "horoscope_data"):
        data = profile.horoscope_data if isinstance(profile.horoscope_data, dict) else {}
        if _truthy_dosham(data.get("dosham")):
            yes_ids.add(profile.user_id)

    genders = dict(User.objects.filter(pk__in=scoped).values_list("pk", "gender"))
    for hp in (
        HoroscopeProfile.objects.filter(user_id__in=scoped)
        .exclude(pr_rasi="")
        .filter(pr_rasi__isnull=False)
        .only("user_id", "pr_rasi")
        .iterator(chunk_size=500)
    ):
        if _chart_has_chovva(hp.pr_rasi, genders.get(hp.user_id)):
            yes_ids.add(hp.user_id)

    if want_yes:
        return qs.filter(pk__in=yes_ids) if yes_ids else qs.none()
    return qs.exclude(pk__in=yes_ids)


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
        _ci_contains("name", search)
        | _ci_contains("matri_id", search)
        | _ci_contains("mobile", search)
        | _ci_contains("reg_no", search)
    )
    digits_only = "".join(ch for ch in search if ch.isdigit())
    if digits_only and digits_only != search:
        search_filter |= _ci_contains("mobile", digits_only)
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
        qs = qs.filter(_ci_contains("matri_id", matri_id))

    name = _qp(request, "name")
    if name:
        qs = qs.filter(_ci_contains("name", name))

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
        qs = qs.filter(_star_match_q(int(pr_star)))
    else:
        star = _qp(request, "star")
        if star:
            if star.isdigit() and 1 <= int(star) <= 27:
                qs = qs.filter(_star_match_q(int(star)))
            else:
                qs = qs.filter(_ci_contains("horoscope_profile__star_name", star))

    rasi_id = _qp(request, "rasi_id")
    if rasi_id.isdigit() and 1 <= int(rasi_id) <= 12:
        qs = _apply_rasi_id_filter(qs, int(rasi_id))
    else:
        rasi = _qp(request, "rasi")
        if rasi:
            mapped = _rasi_id_from_name(rasi)
            if mapped:
                qs = _apply_rasi_id_filter(qs, mapped)
            else:
                qs = qs.filter(_ci_contains("horoscope_profile__rasi_sign", rasi))

    has_horoscope = _qp(request, "has_horoscope")
    if has_horoscope:
        qs = _apply_has_horoscope_filter(qs, has_horoscope)

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
        qs = qs.filter(_rajju_q(rajju))

    dosham = _qp(request, "dosham").lower()
    if dosham in {"true", "1", "yes"}:
        qs = _filter_users_by_dosham(qs, True)
    elif dosham in {"false", "0", "no"}:
        qs = _filter_users_by_dosham(qs, False)

    gender = _qp(request, "gender").upper()
    if gender in {"M", "F", "O"}:
        qs = qs.filter(gender=gender)

    plan = _qp(request, "plan", "plan_id")
    if plan.isdigit():
        qs = qs.filter(user_plan__plan_id=int(plan))
    elif plan:
        qs = qs.filter(_ci_exact("user_plan__plan__name", plan))

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
