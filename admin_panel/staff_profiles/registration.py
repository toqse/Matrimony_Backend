"""
Staff-initiated member registration (user-site equivalent, no OTP).
Creates User + profile sections + optional photo uploads; assigns CustomerStaffAssignment elsewhere.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from rest_framework.exceptions import ValidationError as DRFValidationError

from accounts.models import User
from admin_panel.bulk_upload.services import mobile_exists_in_db, normalize_mobile
from admin_panel.profile_admin.patch_helpers import SECTION_HANDLERS
from admin_panel.subscriptions.models import CustomerStaffAssignment
from profiles.models import UserPhotos, UserProfile
from profiles.utils import get_profile_completion_data, mark_profile_step_completed

SECTION_ORDER = (
    "basic_details",
    "location_details",
    "religion_details",
    "personal_details",
    "family_details",
    "education_details",
    "about_me",
)

FILE_FIELD_ALIASES = {
    "full_photo": "full_photo",
    "passport_photo": "profile_photo",
    "profile_photo": "profile_photo",
    "selfie": "selfie_photo",
    "selfie_photo": "selfie_photo",
    "family_photo": "family_photo",
    "aadhaar_front": "aadhaar_front",
    "aadhaar_back": "aadhaar_back",
}


def _canonical_upload_field_key(raw: str) -> str | None:
    """Map multipart field names (including 'selfie / selfie_photo') to FILE_FIELD_ALIASES keys."""
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    t = re.sub(r"[\s/_\\|,-]+", "_", s)
    t = re.sub(r"_+", "_", t).strip("_")
    if t in FILE_FIELD_ALIASES:
        return t
    synonym_to_canonical = {
        "passport": "passport_photo",
        "selfie_selfie_photo": "selfie_photo",
        "selfiephoto": "selfie_photo",
        "aadhar_front": "aadhaar_front",
        "aadhar_back": "aadhaar_back",
        "aadhaarfront": "aadhaar_front",
        "aadhaarback": "aadhaar_back",
    }
    return synonym_to_canonical.get(t)


def _collect_multipart_files(request) -> dict[str, Any]:
    """Gather uploads from request.FILES and file-like values in request.data (DRF multipart)."""
    files: dict[str, Any] = {}

    def store(orig_key: str, fobj) -> None:
        if not fobj:
            return
        ck = _canonical_upload_field_key(orig_key)
        if ck:
            files[ck] = fobj

    fd = getattr(request, "FILES", None)
    if fd:
        for orig_key in fd:
            for fobj in fd.getlist(orig_key):
                store(orig_key, fobj)

    for orig_key, val in request.data.items():
        if orig_key in ("registration", "data", "payload", "profile"):
            continue
        if isinstance(val, UploadedFile):
            store(orig_key, val)
        elif isinstance(val, (list, tuple)):
            for item in val:
                if isinstance(item, UploadedFile):
                    store(orig_key, item)
                    break

    return files


PROFILE_FOR_VALUES = frozenset(
    {"myself", "son", "daughter", "brother", "sister", "friend", "relative"}
)


def parse_request_data_and_files(request) -> tuple[dict[str, Any], dict[str, Any]]:
    """Merge JSON body or multipart (registration/data/payload JSON + form fields + FILES)."""
    ct = (request.content_type or "").lower()
    if "multipart" in ct:
        merged: dict[str, Any] = {}
        for blob_key in ("registration", "data", "payload", "profile"):
            raw = request.data.get(blob_key)
            if raw is None:
                continue
            if isinstance(raw, str):
                try:
                    merged.update(json.loads(raw))
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in {blob_key}: {e}") from e
            elif isinstance(raw, dict):
                merged.update(raw)
        for key, val in request.data.items():
            if key in ("registration", "data", "payload", "profile"):
                continue
            if key in request.FILES:
                continue
            if isinstance(val, UploadedFile):
                continue
            if isinstance(val, (list, tuple)) and val and isinstance(val[0], UploadedFile):
                continue
            merged[key] = val
        files = _collect_multipart_files(request)
        return merged, files
    return dict(request.data), {}


def _first_drf_error(exc: DRFValidationError) -> str:
    d = exc.detail
    if isinstance(d, dict):
        for v in d.values():
            if isinstance(v, list) and v:
                return str(v[0])
            return str(v)
    if isinstance(d, list) and d:
        return str(d[0])
    return str(d)


META_KEYS_SKIP_SECTIONS = frozenset(
    {
        "name",
        "phone_number",
        "phone",
        "mobile",
        "gender",
        "dob",
        "email",
        "terms_accepted",
        "profile_for",
        "id_verification_consent",
    }
)


def validate_core_create_fields(data: dict) -> tuple[dict[str, str] | None, dict | None]:
    """Returns (errors, None) or (None, normalized_fields)."""
    errors: dict[str, str] = {}

    name = (data.get("name") or "").strip()
    if not name:
        errors["name"] = "Name is required."

    phone = (data.get("phone_number") or data.get("phone") or data.get("mobile") or "").strip()
    mobile = None
    if not phone:
        errors["phone_number"] = "Phone number is required."
    else:
        mobile = normalize_mobile(phone)
        if not mobile or len(mobile) != 10:
            errors["phone_number"] = "Enter a valid 10-digit phone number."
        elif mobile_exists_in_db(mobile):
            errors["phone_number"] = "Phone number already registered."

    gender = (data.get("gender") or "").strip().upper()
    if not gender:
        errors["gender"] = "Gender is required."
    elif gender not in {"M", "F", "O"}:
        errors["gender"] = "Gender must be M, F, or O."

    dob_raw = (data.get("dob") or "").strip()
    dob_iso = None
    if not dob_raw:
        errors["dob"] = "Date of birth is required."
    elif not re.match(r"^\d{2}-\d{2}-\d{4}$", dob_raw):
        errors["dob"] = "Invalid date format. Use DD-MM-YYYY."
    else:
        try:
            dob_iso = datetime.strptime(dob_raw, "%d-%m-%Y").date().isoformat()
        except ValueError:
            errors["dob"] = "Invalid date format. Use DD-MM-YYYY."

    email = (data.get("email") or "").strip()
    if email:
        from django.core.exceptions import ValidationError as DjValidationError
        from django.core.validators import validate_email

        try:
            validate_email(email)
        except DjValidationError:
            errors["email"] = "Invalid email address."

    ta = data.get("terms_accepted")
    if ta is not True and str(ta).strip().lower() not in ("true", "1", "yes"):
        errors["terms_accepted"] = "You must accept the Terms & Conditions and Privacy Policy."

    pf = (data.get("profile_for") or "").strip().lower()
    if pf and pf not in PROFILE_FOR_VALUES:
        errors["profile_for"] = (
            "Invalid profile_for. Use: myself, son, daughter, brother, sister, friend, relative."
        )

    if errors:
        return errors, None
    return None, {
        "name": name,
        "mobile": mobile,
        "gender": gender,
        "dob_iso": dob_iso,
        "email": email or None,
    }


def save_profile_uploads(user: User, files: dict) -> bool:
    """Map incoming file keys to UserPhotos fields. Returns True if any file saved."""
    if not files:
        return False
    photos, _ = UserPhotos.objects.get_or_create(user=user)
    updated = False
    for incoming, attr in FILE_FIELD_ALIASES.items():
        f = files.get(incoming)
        if f:
            setattr(photos, attr, f)
            updated = True
    if updated:
        photos.save()
        mark_profile_step_completed(user, "photos")
    return updated


def apply_profile_sections(user: User, data: dict) -> None:
    """Apply SECTION_HANDLERS keys present in data (order stable)."""
    for key in SECTION_ORDER:
        if key not in data or data[key] is None:
            continue
        payload = data[key]
        if key == "about_me":
            if isinstance(payload, str):
                if len(payload) > 500:
                    raise DRFValidationError({"about_me": "About me must be 500 characters or fewer."})
                payload = {"about_me": payload}
            elif isinstance(payload, dict):
                text = payload.get("about_me") or ""
                if len(text) > 500:
                    raise DRFValidationError({"about_me": "About me must be 500 characters or fewer."})
            else:
                raise DRFValidationError({key: "Expected a string or object for about_me."})
        elif not isinstance(payload, dict):
            raise DRFValidationError({key: "Expected a JSON object for this section."})
        handler = SECTION_HANDLERS[key]
        try:
            handler(user, payload)
        except DRFValidationError as e:
            raise DRFValidationError({key: _first_drf_error(e)}) from e


def create_user_and_profile_sections(
    *,
    name: str,
    mobile: str,
    gender: str,
    dob_iso: str,
    email: str | None,
    branch_pk: int,
    data: dict,
    files: dict,
    staff,
) -> User:
    """Transactional create: User + optional sections + photos. OTP skipped (mobile_verified=True)."""
    dob = date.fromisoformat(dob_iso)
    pwd = User.objects.make_random_password()
    with transaction.atomic():
        user = User.objects.create_user(
            email=(email or None) or None,
            mobile=mobile,
            password=pwd,
            name=name,
            dob=dob,
            gender=gender,
            branch_id=branch_pk,
        )
        user.role = "user"
        user.is_active = True
        user.mobile_verified = True
        user.email_verified = bool(email)
        user.save(
            update_fields=[
                "role",
                "is_active",
                "mobile_verified",
                "email_verified",
                "updated_at",
            ]
        )
        UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "location_completed": False,
                "religion_completed": False,
                "personal_completed": False,
                "family_completed": False,
                "education_completed": False,
                "about_completed": False,
                "photos_completed": False,
            },
        )

        basic = dict(data.get("basic_details") or {})
        pf = (data.get("profile_for") or "").strip().lower()
        if pf:
            basic.setdefault("profile_for", pf)
        gmap = {"M": "male", "F": "female", "O": "other"}
        if "gender" not in basic:
            basic["gender"] = gmap.get(gender, "other")
        if basic:
            try:
                SECTION_HANDLERS["basic_details"](user, basic)
            except DRFValidationError as e:
                raise DRFValidationError({"basic_details": _first_drf_error(e)}) from e

        section_data = {
            k: v
            for k, v in data.items()
            if k not in META_KEYS_SKIP_SECTIONS and k != "basic_details"
        }
        apply_profile_sections(user, section_data)

        save_profile_uploads(user, files)

        CustomerStaffAssignment.objects.update_or_create(user=user, defaults={"staff": staff})

        completion = get_profile_completion_data(user)
        user.is_registration_profile_completed = completion["profile_status"] == "completed"
        user.save(update_fields=["is_registration_profile_completed", "updated_at"])

    return user
