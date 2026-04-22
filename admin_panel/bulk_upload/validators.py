import re
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Q

from accounts.models import User
from master.models import (
    Caste,
    City,
    Country,
    District,
    Education,
    EducationSubject,
    IncomeRange,
    MaritalStatus,
    MotherTongue,
    Occupation,
    Religion,
    State,
)

CACHE_PREFIX = "bulk_upload:v2:"
CACHE_TTL = 60 * 60
ASYNC_ROW_THRESHOLD = 50
VALID_COMPLEXIONS = {"Very Fair","Fair","Wheatish","Wheatish Brown","Dark","Other"}
SPECIAL_MARITALS = {"divorced", "widowed", "separated"}
MAX_AVAILABLE_VALUES_IN_ERROR = 20


def normalize_gender(raw: str) -> str:
    """Accept M/F/O or common full words from spreadsheets."""
    s = (raw or "").strip().upper()
    if s in {"M", "MALE", "MAN", "BOY"}:
        return "M"
    if s in {"F", "FEMALE", "WOMAN", "GIRL"}:
        return "F"
    if s in {"O", "OTHER", "OTHERS"}:
        return "O"
    return s


def normalize_phone(raw: str) -> str | None:
    s = "".join(ch for ch in (raw or "") if ch.isdigit())
    if len(s) == 12 and s.startswith("91"):
        s = s[-10:]
    if len(s) == 11 and s.startswith("0"):
        s = s[-10:]
    if len(s) != 10:
        return None
    return s


def _db_phone_exists(phone10: str) -> bool:
    return User.objects.filter(
        Q(mobile=phone10) | Q(mobile="91" + phone10) | Q(mobile="+91" + phone10)
    ).exists()


def _parse_dob(value: str):
    text = (value or "").strip()
    if not text:
        return None
    try:
        dob = datetime.strptime(text, "%d-%m-%Y").date()
    except ValueError:
        return "__invalid__"
    if dob > datetime.now().date():
        return "__future__"
    return dob


def _resolve_name(model, name: str):
    if not (name or "").strip():
        return None
    return model.objects.filter(name__iexact=name.strip(), is_active=True).first()


def _active_names(model, filters: dict[str, Any] | None = None) -> list[str]:
    qs = model.objects.filter(is_active=True)
    if filters:
        qs = qs.filter(**filters)
    return list(qs.order_by("name").values_list("name", flat=True))


def _available_values_clause(values: list[str]) -> str:
    if not values:
        return "No active values are configured in backend."
    shown = values[:MAX_AVAILABLE_VALUES_IN_ERROR]
    suffix = ""
    if len(values) > MAX_AVAILABLE_VALUES_IN_ERROR:
        suffix = f" (+{len(values) - MAX_AVAILABLE_VALUES_IN_ERROR} more)"
    return f"{', '.join(shown)}{suffix}"


def _not_found_with_available_message(entity_label: str, available_label: str, values: list[str]) -> str:
    return (
        f"{entity_label} not found. "
        f"Available {available_label} are: {_available_values_clause(values)}"
    )


def _resolve_location(country: str, state: str, district: str, city: str):
    c = _resolve_name(Country, country)
    s = None
    d = None
    ci = None
    if c and (state or "").strip():
        s = State.objects.filter(country=c, name__iexact=state.strip(), is_active=True).first()
    if s and (district or "").strip():
        d = District.objects.filter(state=s, name__iexact=district.strip(), is_active=True).first()
    if d and (city or "").strip():
        ci = City.objects.filter(district=d, name__iexact=city.strip(), is_active=True).first()
    return c, s, d, ci


def _parse_non_negative_integer_optional(raw: str):
    text = (raw or "").strip()
    if not text:
        return 0, True
    try:
        dec = Decimal(text)
    except (InvalidOperation, ValueError):
        return None, False
    if dec < 0:
        return None, False
    if dec != dec.to_integral_value():
        return None, False
    return int(dec), True


def validate_rows(data_rows: list[dict[str, str]]):
    errors: list[dict[str, Any]] = []
    valid_payloads: list[dict[str, Any]] = []
    seen_phone: dict[str, int] = {}

    non_empty: list[tuple[int, dict[str, str]]] = []
    row_no = 2
    for r in data_rows:
        if any((v or "").strip() for v in r.values()):
            non_empty.append((row_no, r))
        row_no += 1

    for row, r in non_empty:
        row_err: list[dict[str, Any]] = []
        name = (r.get("name") or "").strip()
        if not name:
            row_err.append({"row": row, "field": "name", "message": "Name is required"})

        phone_raw = (r.get("phone") or "").strip()
        phone = None
        if phone_raw:
            phone = normalize_phone(phone_raw)
            if not phone:
                row_err.append({"row": row, "field": "phone", "message": "Phone must be 10 digits"})
            elif phone in seen_phone:
                row_err.append({"row": row, "field": "phone", "message": "Phone number already appears in file"})
            elif _db_phone_exists(phone):
                row_err.append({"row": row, "field": "phone", "message": "Phone number already exists"})
            seen_phone[phone or ""] = row

        email = (r.get("email") or "").strip()
        if email:
            try:
                validate_email(email)
            except ValidationError:
                row_err.append({"row": row, "field": "email", "message": "Invalid email address"})

        dob = _parse_dob(r.get("dob") or "")
        if dob == "__invalid__":
            row_err.append({"row": row, "field": "dob", "message": "Date of Birth must be DD-MM-YYYY"})
        elif dob == "__future__":
            row_err.append({"row": row, "field": "dob", "message": "Date of Birth cannot be in the future"})

        gender = normalize_gender(r.get("gender") or "")
        if gender and gender not in {"M", "F", "O"}:
            row_err.append(
                {
                    "row": row,
                    "field": "gender",
                    "message": "Gender must be M, F, O (or Male/Female/Other)",
                }
            )

        religion_name = (r.get("religion") or "").strip()
        religion = _resolve_name(Religion, religion_name) if religion_name else None
        if religion_name and not religion:
            row_err.append(
                {
                    "row": row,
                    "field": "religion",
                    "message": "Invalid religion",
                }
            )

        caste_name = (r.get("caste") or "").strip()
        caste = None
        if caste_name and not religion_name:
            row_err.append({"row": row, "field": "caste", "message": "Caste requires Religion"})
        elif caste_name and religion:
            caste = Caste.objects.filter(religion=religion, name__iexact=caste_name, is_active=True).first()
            if not caste:
                row_err.append(
                    {
                        "row": row,
                        "field": "caste",
                        "message": _not_found_with_available_message(
                            "Caste",
                            f"Castes for {religion.name}",
                            _active_names(Caste, {"religion": religion}),
                        ),
                    }
                )

        mt_raw = (r.get("mother_tongue") or "").strip()
        mother_tongue = _resolve_name(MotherTongue, mt_raw)
        if mt_raw and not mother_tongue:
            row_err.append(
                {
                    "row": row,
                    "field": "mother_tongue",
                    "message": "Invalid mother_tongue",
                }
            )

        marital_name = (r.get("marital_status") or "").strip()
        marital = _resolve_name(MaritalStatus, marital_name) if marital_name else None
        if marital_name and not marital:
            row_err.append(
                {
                    "row": row,
                    "field": "marital_status",
                    "message": _not_found_with_available_message(
                        "Marital Status",
                        "Marital Statuses",
                        _active_names(MaritalStatus),
                    ),
                }
            )

        has_children_raw = (r.get("has_children") or "").strip().lower()
        has_children = None
        if has_children_raw:
            if has_children_raw in {"yes", "y", "true", "1"}:
                has_children = True
            elif has_children_raw in {"no", "n", "false", "0"}:
                has_children = False
            else:
                row_err.append({"row": row, "field": "has_children", "message": "Has Children must be Yes or No"})

        if marital_name.lower() in SPECIAL_MARITALS and has_children is None:
            row_err.append(
                {"row": row, "field": "has_children", "message": "Has Children is required for divorced/widowed/separated"}
            )

        noc_raw = (r.get("number_of_children") or "").strip()
        noc = 0
        if noc_raw:
            try:
                noc = int(noc_raw)
                if noc < 0:
                    raise ValueError
            except ValueError:
                row_err.append({"row": row, "field": "number_of_children", "message": "Number of Children must be >= 0"})
        if has_children is True and not noc_raw:
            row_err.append(
                {"row": row, "field": "number_of_children", "message": "Number of Children is required when Has Children is Yes"}
            )

        height_raw = (r.get("height_cm") or "").strip()
        height_cm = None
        if height_raw:
            try:
                height_cm = int(float(height_raw))
            except (ValueError, TypeError):
                height_cm = None
            if height_cm is None or not (100 <= height_cm <= 250):
                row_err.append({"row": row, "field": "height_cm", "message": "Height must be between 100 and 250"})

        weight_raw = (r.get("weight_kg") or "").strip()
        weight = None
        if weight_raw:
            try:
                weight = Decimal(weight_raw)
            except (InvalidOperation, ValueError):
                row_err.append({"row": row, "field": "weight_kg", "message": "Weight must be numeric"})

        complexion = (r.get("complexion") or "").strip()
        if complexion and complexion not in VALID_COMPLEXIONS:
            row_err.append(
                {"row": row, "field": "complexion", "message": "Complexion must be Fair/Wheatish/Dark/Very Fair"}
            )

        about_me = (r.get("about_me") or "").strip()
        if len(about_me) > 500:
            row_err.append({"row": row, "field": "about_me", "message": "About Me must be at most 500 characters"})

        num_brothers, ok_num_brothers = _parse_non_negative_integer_optional(
            r.get("num_brothers") or ""
        )
        if not ok_num_brothers:
            row_err.append(
                {
                    "row": row,
                    "field": "num_brothers",
                    "message": "Must be a non-negative integer.",
                }
            )

        num_married_brothers, ok_num_married_brothers = _parse_non_negative_integer_optional(
            r.get("num_married_brothers") or ""
        )
        if not ok_num_married_brothers:
            row_err.append(
                {
                    "row": row,
                    "field": "num_married_brothers",
                    "message": "Must be a non-negative integer.",
                }
            )

        num_sisters, ok_num_sisters = _parse_non_negative_integer_optional(
            r.get("num_sisters") or ""
        )
        if not ok_num_sisters:
            row_err.append(
                {
                    "row": row,
                    "field": "num_sisters",
                    "message": "Must be a non-negative integer.",
                }
            )

        num_married_sisters, ok_num_married_sisters = _parse_non_negative_integer_optional(
            r.get("num_married_sisters") or ""
        )
        if not ok_num_married_sisters:
            row_err.append(
                {
                    "row": row,
                    "field": "num_married_sisters",
                    "message": "Must be a non-negative integer.",
                }
            )

        c, s, d, ci = _resolve_location(r.get("country"), r.get("state"), r.get("district"), r.get("city"))
        country_raw = (r.get("country") or "").strip()
        if country_raw and not c:
            row_err.append({"row": row, "field": "country", "message": "Invalid country"})
        state_raw = (r.get("state") or "").strip()
        if state_raw and country_raw and c and not s:
            row_err.append({"row": row, "field": "state", "message": "Invalid state"})

        highest_education = _resolve_name(Education, r.get("highest_education") or "")
        education_subject = _resolve_name(EducationSubject, r.get("education_subject") or "")
        occupation = _resolve_name(Occupation, r.get("occupation") or "")
        annual_income = _resolve_name(IncomeRange, r.get("annual_income") or "")
        if (r.get("highest_education") or "").strip() and not highest_education:
            row_err.append(
                {
                    "row": row,
                    "field": "highest_education",
                    "message": _not_found_with_available_message(
                        "Highest Education",
                        "Highest Education values",
                        _active_names(Education),
                    ),
                }
            )
        if (r.get("education_subject") or "").strip() and not education_subject:
            row_err.append(
                {
                    "row": row,
                    "field": "education_subject",
                    "message": _not_found_with_available_message(
                        "Education Subject",
                        "Education Subjects",
                        _active_names(EducationSubject),
                    ),
                }
            )
        if (r.get("occupation") or "").strip() and not occupation:
            row_err.append(
                {
                    "row": row,
                    "field": "occupation",
                    "message": "Invalid occupation",
                }
            )
        if (r.get("annual_income") or "").strip() and not annual_income:
            row_err.append(
                {
                    "row": row,
                    "field": "annual_income",
                    "message": _not_found_with_available_message(
                        "Annual Income",
                        "Annual Income ranges",
                        _active_names(IncomeRange),
                    ),
                }
            )

        errors.extend(row_err)
        if row_err:
            continue

        valid_payloads.append(
            {
                "row": row,
                "name": name,
                "phone": phone,
                "email": email or None,
                "dob": dob.isoformat() if dob else None,
                "gender": gender or "",
                "partner_preference": (r.get("partner_preference") or "").strip(),
                "country_id": c.id if c else None,
                "state_id": s.id if s else None,
                "district_id": d.id if d else None,
                "city_id": ci.id if ci else None,
                "address": (r.get("address") or "").strip(),
                "religion_id": religion.id if religion else None,
                "caste_id": caste.id if caste else None,
                "mother_tongue_id": mother_tongue.id if mother_tongue else None,
                "marital_status_id": marital.id if marital else None,
                "has_children": has_children if has_children is not None else False,
                "number_of_children": noc,
                "height_cm": height_cm,
                "weight_kg": str(weight) if weight is not None else None,
                "complexion": complexion,
                "highest_education_id": highest_education.id if highest_education else None,
                "education_subject_id": education_subject.id if education_subject else None,
                "employment": (r.get("employment") or "").strip(),
                "occupation_id": occupation.id if occupation else None,
                "annual_income_id": annual_income.id if annual_income else None,
                "about_me": about_me,
                "family_type": (r.get("family_type") or "").strip(),
                "father_name": (r.get("father_name") or "").strip(),
                "father_occupation": (r.get("father_occupation") or "").strip(),
                "mother_name": (r.get("mother_name") or "").strip(),
                "mother_occupation": (r.get("mother_occupation") or "").strip(),
                "family_status": (r.get("family_status") or "").strip(),
                "num_brothers": int(num_brothers or 0),
                "num_married_brothers": int(num_married_brothers or 0),
                "num_sisters": int(num_sisters or 0),
                "num_married_sisters": int(num_married_sisters or 0),
                "about_family": (r.get("about_family") or "").strip(),
            }
        )

    total_rows = len(non_empty)
    error_rows = len({e["row"] for e in errors})
    valid_rows = total_rows - error_rows
    return total_rows, valid_rows, error_rows, errors, valid_payloads


def cache_validation_payload(admin_user_id: int, job_id: int, rows: list[dict[str, Any]]) -> str:
    token = secrets.token_urlsafe(32)
    cache.set(
        CACHE_PREFIX + token,
        {"admin_user_id": int(admin_user_id), "job_id": int(job_id), "rows": rows},
        CACHE_TTL,
    )
    return token


def get_cached_payload(token: str) -> dict[str, Any] | None:
    return cache.get(CACHE_PREFIX + token)


def delete_cached_payload(token: str):
    cache.delete(CACHE_PREFIX + token)
