"""Row-level orchestrator: build a normalized payload, then persist it."""
from __future__ import annotations

from typing import Optional

from accounts.models import User
from profiles.models import (
    UserEducation,
    UserFamily,
    UserLocation,
    UserPersonal,
    UserPhotos,
    UserProfile,
    UserReligion,
)
from profiles.utils import get_profile_completion_data

from .geocode import PlaceGeocoder, place_of_birth_from_row
from .horoscope import resolve_padam, resolve_star, star_lookup, upsert_horoscope_profile
from .masters import MasterResolver, normalize_complexion_name
from .normalize import (
    clean,
    parent_name,
    parse_bool,
    parse_decimal,
    parse_dob,
    parse_email,
    parse_gender,
    parse_int,
    parse_phone,
    time_of_birth_from_row,
)


class LegacyImporter:
    """Single-row import orchestrator.

    Use `build_payload` to convert a raw CSV row dict into a normalized
    payload (with master FKs resolved); use `save` to persist it. Both are
    decoupled so the management command can dry-run by skipping `save`.
    """

    def __init__(
        self,
        *,
        dry_run: bool = False,
        branch=None,
        skip_existing: bool = True,
        auto_create_masters: bool = True,
    ):
        self.dry_run = dry_run
        self.branch = branch
        self.skip_existing = skip_existing
        # In dry-run we never auto-create masters: validating shouldn't pollute the DB.
        self.masters = MasterResolver(auto_create=auto_create_masters and not dry_run)
        self.seen_phones: set[str] = set()
        self.seen_emails: set[str] = set()
        self.stars = star_lookup()
        self._existing_mobiles: set[str] | None = None
        self._existing_emails: set[str] | None = None
        self._geocoder = PlaceGeocoder()

    def _ensure_existing_lookups(self) -> None:
        """Load existing mobiles/emails once — avoids N+1 queries on large CSVs."""
        if not self.skip_existing:
            return
        if self._existing_mobiles is None:
            self._existing_mobiles = {
                (m or "").strip()
                for m in User.objects.exclude(mobile__isnull=True)
                .exclude(mobile="")
                .values_list("mobile", flat=True)
            }
        if self._existing_emails is None:
            self._existing_emails = {
                (e or "").strip().lower()
                for e in User.objects.exclude(email__isnull=True)
                .exclude(email="")
                .values_list("email", flat=True)
            }

    def _phone_exists(self, phone: str) -> bool:
        self._ensure_existing_lookups()
        assert self._existing_mobiles is not None
        return (
            phone in self._existing_mobiles
            or f"91{phone}" in self._existing_mobiles
            or f"+91{phone}" in self._existing_mobiles
        )

    def _email_exists(self, email: str) -> bool:
        self._ensure_existing_lookups()
        assert self._existing_emails is not None
        return email.lower() in self._existing_emails

    def build_payload(self, row_number: int, row: dict) -> tuple[Optional[dict], str]:
        """Return (payload, '') for valid rows; (None, reason) for skipped rows."""
        name = clean(row.get("name"))
        gender = parse_gender(row.get("gender"))
        phone = parse_phone(row.get("phone number"))
        email = parse_email(row.get("email"))
        dob = parse_dob(row.get("date of birth"))

        if not name or name.upper() == "M":
            return None, "missing_or_invalid_name"
        if gender not in {"M", "F", "O"}:
            return None, "invalid_gender"

        if phone:
            if phone in self.seen_phones:
                return None, "duplicate_phone_in_file"
            self.seen_phones.add(phone)
            if self.skip_existing and self._phone_exists(phone):
                return None, "phone_exists_in_db"

        if email:
            if email in self.seen_emails:
                return None, "duplicate_email_in_file"
            self.seen_emails.add(email)
            if self.skip_existing and self._email_exists(email):
                return None, "email_exists_in_db"

        religion = self.masters.religion(row.get("religion"))
        caste_obj = self.masters.caste(religion, row.get("caste"))
        country, state, district, city = self.masters.location(
            row.get("country"),
            row.get("state"),
            row.get("district"),
            row.get("city"),
        )

        height_cm_raw = parse_int(row.get("height (cm)"))
        height_cm = height_cm_raw if 100 <= height_cm_raw <= 250 else None
        complexion = normalize_complexion_name(row.get("complexion"))

        star_number, star_warning = resolve_star(row.get("star"), self.stars)

        # Legacy export puts the *role* (e.g. "ACCOUNTS STAFF") in `Occupation`
        # and the company name (e.g. "ASWATHY PETROL PUMB") in `Employment`.
        # Map them straight across so the new model gets sensible values.
        payload = {
            "row": row_number,
            "name": name,
            "phone": phone,
            "email": email,
            "dob": dob,
            "gender": gender,
            "partner_preference": clean(row.get("partner preference")),
            "country": country,
            "state": state,
            "district": district,
            "city": city,
            "address": clean(row.get("address")),
            "religion": religion,
            "caste": caste_obj,
            "caste_text": clean(row.get("caste")),
            "mother_tongue": self.masters.mother_tongue(row.get("mother toungue")),
            "marital_status": self.masters.marital_status(row.get("marital status")),
            "has_children": parse_bool(row.get("has children")),
            "number_of_children": parse_int(row.get("number of children")),
            "height": self.masters.height(height_cm),
            "height_cm": height_cm,
            "weight": parse_decimal(row.get("weight (kg)")),
            "complexion": complexion,
            "highest_education": self.masters.education(row.get("highest education")),
            "education_subject": self.masters.education_subject(row.get("education subject")),
            "occupation": self.masters.occupation(row.get("occupation")),
            "annual_income": self.masters.income_range(row.get("annual income")),
            "employment_status": clean(row.get("occupation")),
            "company": clean(row.get("employment")),
            "about_me": clean(row.get("about me")),
            "family_type": clean(row.get("family type")),
            "father_name": parent_name(row.get("father's name")),
            "father_occupation": clean(row.get("father's occupation")),
            "mother_name": parent_name(row.get("mother's name")),
            "mother_occupation": clean(row.get("mother's occupation")),
            "family_status": clean(row.get("family status")),
            "brothers": parse_int(row.get("number of brothers")),
            "married_brothers": parse_int(row.get("number of married brothers")),
            "sisters": parse_int(row.get("number of sisters")),
            "married_sisters": parse_int(row.get("number of married sisters")),
            "about_family": clean(row.get("about my family")),
            "pr_rasi": clean(row.get("horochart")),
            "pr_amsa": clean(row.get("amsachart")),
            "pr_bhav": clean(row.get("bhavchart")),
            "pr_dasabalance": parse_int(row.get("sishta_dur")),
            "pr_star": star_number,
            "pr_pada": resolve_padam(row.get("padam")),
            "star_warning": star_warning,
            "place_of_birth": place_of_birth_from_row(row),
            "time_of_birth": time_of_birth_from_row(row),
        }
        return payload, ""

    def save(self, payload: dict) -> Optional[User]:
        """Persist a built payload to the database. No-op when dry_run=True."""
        if self.dry_run:
            return None

        user = User(
            name=payload["name"],
            mobile=payload["phone"],
            email=payload["email"],
            dob=payload["dob"],
            gender=payload["gender"],
            branch=self.branch,
            role="user",
            is_active=True,
            mobile_verified=bool(payload["phone"]),
            email_verified=bool(payload["email"]),
        )
        user.set_password(User.objects.make_random_password())
        user.save()

        place_of_birth = payload.get("place_of_birth") or ""
        time_of_birth = payload.get("time_of_birth")
        birth_latitude = None
        birth_longitude = None
        if place_of_birth:
            coords = self._geocoder.resolve(place_of_birth)
            if coords:
                birth_latitude, birth_longitude = coords
                payload["birth_latitude"] = birth_latitude
                payload["birth_longitude"] = birth_longitude

        has_chart_data = bool(
            payload["pr_rasi"]
            or payload["pr_amsa"]
            or payload["pr_bhav"]
            or payload["pr_star"]
        )
        has_horoscope = bool(has_chart_data or place_of_birth or time_of_birth)
        UserProfile.objects.update_or_create(
            user=user,
            defaults={
                "about_me": payload["about_me"],
                "has_horoscope": has_horoscope,
                "place_of_birth": place_of_birth,
                "time_of_birth": time_of_birth,
                "birth_latitude": birth_latitude,
                "birth_longitude": birth_longitude,
                "birth_timezone": 5.5
                if (place_of_birth or time_of_birth or has_chart_data)
                else None,
            },
        )
        UserLocation.objects.update_or_create(
            user=user,
            defaults={
                "country": payload["country"],
                "state": payload["state"],
                "district": payload["district"],
                "city": payload["city"],
                "address": payload["address"],
            },
        )
        UserReligion.objects.update_or_create(
            user=user,
            defaults={
                "religion": payload["religion"],
                "caste_fk": payload["caste"],
                "caste": payload["caste_text"],
                "mother_tongue": payload["mother_tongue"],
                "partner_religion_preference": payload["partner_preference"],
            },
        )
        UserPersonal.objects.update_or_create(
            user=user,
            defaults={
                "marital_status": payload["marital_status"],
                "has_children": payload["has_children"] or payload["number_of_children"] > 0,
                "number_of_children": payload["number_of_children"],
                "height": payload["height"],
                "height_text": f'{payload["height_cm"]} cm' if payload["height_cm"] else "",
                "weight": payload["weight"],
                "colour": payload["complexion"],
            },
        )
        UserFamily.objects.update_or_create(
            user=user,
            defaults={
                "father_name": payload["father_name"],
                "father_occupation": payload["father_occupation"],
                "mother_name": payload["mother_name"],
                "mother_occupation": payload["mother_occupation"],
                "brothers": payload["brothers"],
                "married_brothers": payload["married_brothers"],
                "sisters": payload["sisters"],
                "married_sisters": payload["married_sisters"],
                "about_family": payload["about_family"],
                "family_type": payload["family_type"],
                "family_status": payload["family_status"],
            },
        )
        UserEducation.objects.update_or_create(
            user=user,
            defaults={
                "highest_education": payload["highest_education"],
                "education_subject": payload["education_subject"],
                "occupation": payload["occupation"],
                "annual_income": payload["annual_income"],
                "employment_status": payload["employment_status"],
                "company": payload["company"],
            },
        )
        UserPhotos.objects.get_or_create(user=user)

        upsert_horoscope_profile(user, payload)

        completion = get_profile_completion_data(user)
        user.is_registration_profile_completed = completion["profile_status"] == "completed"
        user.save(update_fields=["is_registration_profile_completed", "updated_at"])
        return user
