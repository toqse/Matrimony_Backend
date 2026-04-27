from datetime import date
from decimal import Decimal, InvalidOperation

from celery import shared_task
from django.db import IntegrityError, transaction

from accounts.models import User
from profiles.models import (
    UserEducation,
    UserFamily,
    UserLocation,
    UserPersonal,
    UserProfile,
    UserReligion,
)
from profiles.utils import get_profile_completion_data

from .models import BulkUploadJob
from .validators import delete_cached_payload, get_cached_payload, normalize_gender


def _import_single_row(payload: dict, branch_id: int | None):
    # Debug: show normalized row data before saving.
    # (Intentional print for troubleshooting bulk upload issues.)
    print("BULK_UPLOAD_ROW:", payload)

    # Payload keys vary slightly across older/newer templates & validators.
    mobile = (
        payload.get("phone")
        or payload.get("phone_number")
        or payload.get("mobile")
        or payload.get("mobile_number")
        or None
    )
    dob_raw = payload.get("dob") or payload.get("date_of_birth") or payload.get("date of birth") or None
    dob = date.fromisoformat(dob_raw) if dob_raw else None
    g = normalize_gender(payload.get("gender") or "")
    if g not in ("M", "F", "O"):
        g = ""
    user = User(
        name=payload.get("name") or "",
        mobile=mobile,
        email=payload.get("email") or None,
        dob=dob,
        gender=g,
        role="user",
        branch_id=branch_id,
        is_active=True,
        mobile_verified=True,
        email_verified=bool(payload.get("email")),
        is_registration_profile_completed=False,
    )
    user.set_password(User.objects.make_random_password())
    user.save()

    profile, _ = UserProfile.objects.get_or_create(user=user)
    if payload.get("about_me"):
        profile.about_me = payload["about_me"]
    if payload.get("partner_preference"):
        profile.about_completed = True
    profile.save()

    UserLocation.objects.update_or_create(
        user=user,
        defaults={
            "country_id": payload.get("country_id"),
            "state_id": payload.get("state_id"),
            "district_id": payload.get("district_id"),
            "city_id": payload.get("city_id"),
            "address": payload.get("address") or "",
        },
    )
    UserReligion.objects.update_or_create(
        user=user,
        defaults={
            "religion_id": payload.get("religion_id"),
            "caste_fk_id": payload.get("caste_id"),
            "mother_tongue_id": payload.get("mother_tongue_id"),
            "partner_religion_preference": payload.get("partner_preference") or "",
        },
    )

    weight = None
    if payload.get("weight_kg"):
        try:
            weight = Decimal(str(payload["weight_kg"]))
        except (InvalidOperation, ValueError):
            weight = None

    UserPersonal.objects.update_or_create(
        user=user,
        defaults={
            "marital_status_id": payload.get("marital_status_id"),
            "has_children": bool(payload.get("has_children")),
            "number_of_children": int(payload.get("number_of_children") or 0),
            "height_text": f'{payload["height_cm"]} cm' if payload.get("height_cm") else "",
            "weight": weight,
            "colour": payload.get("complexion") or "",
        },
    )
    UserEducation.objects.update_or_create(
        user=user,
        defaults={
            "highest_education_id": payload.get("highest_education_id"),
            "education_subject_id": payload.get("education_subject_id"),
            "employment_status": payload.get("employment") or "",
            "occupation_id": payload.get("occupation_id"),
            "annual_income_id": payload.get("annual_income_id"),
        },
    )

    UserFamily.objects.update_or_create(
        user=user,
        defaults={
            "family_type": payload.get("family_type") or "",
            "father_name": payload.get("father_name") or "",
            "father_status": payload.get("father_status") or "",
            "father_occupation": payload.get("father_occupation") or "",
            "mother_name": payload.get("mother_name") or "",
            "mother_status": payload.get("mother_status") or "",
            "mother_occupation": payload.get("mother_occupation") or "",
            "family_status": payload.get("family_status") or "",
            "brothers": int(payload.get("num_brothers") or 0),
            "married_brothers": int(payload.get("num_married_brothers") or 0),
            "sisters": int(payload.get("num_sisters") or 0),
            "married_sisters": int(payload.get("num_married_sisters") or 0),
            "about_family": payload.get("about_family") or "",
        },
    )
    completion = get_profile_completion_data(user)
    user.is_registration_profile_completed = completion["profile_status"] == "completed"
    user.save(update_fields=["is_registration_profile_completed", "updated_at"])


def run_import_job(job_id: int, token: str, admin_user_id: int, branch_id: int | None):
    job = BulkUploadJob.objects.filter(pk=job_id).first()
    if not job:
        return {"ok": False, "error": "Bulk upload job not found"}

    cached = get_cached_payload(token)
    if not cached:
        job.mark_failed("Invalid or expired validation token")
        return {"ok": False, "error": "Invalid or expired validation token"}
    if int(cached.get("admin_user_id")) != int(admin_user_id):
        job.mark_failed("Validation token does not belong to this user")
        return {"ok": False, "error": "Validation token does not belong to this user"}
    if int(cached.get("job_id")) != int(job_id):
        job.mark_failed("Validation token does not belong to this job")
        return {"ok": False, "error": "Validation token does not belong to this job"}

    rows = cached.get("rows") or []
    job.mark_processing()
    imported = 0
    failed: list[dict] = []

    for row in rows:
        try:
            with transaction.atomic():
                _import_single_row(row, branch_id)
            imported += 1
        except IntegrityError as exc:
            failed.append({"row": row.get("row"), "field": "non_field_error", "message": str(exc)})
        except Exception as exc:
            failed.append({"row": row.get("row"), "field": "non_field_error", "message": str(exc)})

    job.mark_completed(imported, failed)
    delete_cached_payload(token)
    return {"ok": True, "imported": imported, "failed": failed}


@shared_task(bind=True, name="admin_panel.bulk_upload.bulk_import_profiles")
def bulk_import_profiles_task(self, job_id: int, token: str, admin_user_id: int, branch_id: int | None):
    return run_import_job(job_id, token, admin_user_id, branch_id)
