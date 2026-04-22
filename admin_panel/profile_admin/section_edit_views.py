"""
Platform-admin-only PATCH endpoints for editing a member profile by matri_id,
one section at a time. Reuses serializers from /api/v1/profile/* flows.
Target user is always resolved from matri_id — never request.user (member).
"""
from __future__ import annotations

from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from admin_panel.audit_log.models import AuditLog
from admin_panel.audit_log.utils import create_audit_log
from admin_panel.auth.models import AdminUser
from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.permissions import IsAdminUser
from admin_panel.staff_profiles.registration import parse_request_data_and_files, save_profile_uploads
from profiles.models import UserEducation, UserLocation, UserPersonal, UserPhotos, UserProfile, UserReligion
from profiles.serializers import (
    AboutDetailsUpdateSerializer,
    BasicDetailsReadSerializer,
    BasicDetailsUpdateSerializer,
    EducationDetailsReadSerializer,
    EducationDetailsUpdateSerializer,
    LocationDetailsReadSerializer,
    LocationDetailsUpdateSerializer,
    PersonalDetailsReadSerializer,
    PersonalDetailsUpdateSerializer,
    PhotosDetailsReadSerializer,
    ReligionDetailsReadSerializer,
    ReligionDetailsUpdateSerializer,
    UserPhotosSerializer,
    empty_education_details_read_data,
    empty_location_details_read_data,
    empty_religion_details_read_data,
)
from profiles.utils import get_profile_completion_data, mark_profile_step_completed, sync_profile_completion_flags


def _target_member(matri_id: str) -> tuple[User | None, Response | None]:
    u = User.objects.filter(matri_id__iexact=(matri_id or "").strip(), role="user").first()
    if not u:
        return None, Response(
            {"success": False, "error": {"code": 404, "message": "Profile not found"}},
            status=status.HTTP_404_NOT_FOUND,
        )
    return u, None


def _sync_registration_done(user: User) -> None:
    sync_profile_completion_flags(user)
    completion = get_profile_completion_data(user)
    user.is_registration_profile_completed = completion["profile_status"] == "completed"
    user.save(update_fields=["is_registration_profile_completed", "updated_at"])


def _log_admin_profile_section(request, target_user: User, section_label: str) -> None:
    actor = request.user
    staff_nm = (getattr(actor, "name", "") or "").strip() if isinstance(actor, AdminUser) else ""
    profile_nm = (target_user.name or "").strip() or (target_user.matri_id or "member")
    mid = (target_user.matri_id or "").strip()
    create_audit_log(
        request,
        action=AuditLog.ACTION_UPDATE_PROFILE,
        resource=f"profile:{mid}" if mid else f"user:{target_user.id}",
        details=f"{staff_nm} updated {section_label} for {profile_nm}.",
        target_profile_name=profile_nm,
        action_type=AuditLog.ACTION_TYPE_UPDATE_PROFILE,
    )


class AdminProfileBasicSectionView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminUser]
    parser_classes = [JSONParser]

    def patch(self, request, matri_id):
        user, err = _target_member(matri_id)
        if err:
            return err
        ser = BasicDetailsUpdateSerializer(user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        try:
            ser.save()
        except IntegrityError:
            raise DRFValidationError({"email": ["Email already exists. Please use a different email."]})
        _sync_registration_done(user)
        _log_admin_profile_section(request, user, "basic details")
        return Response({"success": True, "data": BasicDetailsReadSerializer(ser.instance).data})


class AdminProfileLocationSectionView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminUser]
    parser_classes = [JSONParser]

    def patch(self, request, matri_id):
        user, err = _target_member(matri_id)
        if err:
            return err
        ser = LocationDetailsUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        defaults = {"address": ser.validated_data.get("address", "")}
        for k in ("country_id", "state_id", "district_id", "city_id"):
            if ser.validated_data.get(k) is not None:
                defaults[k] = ser.validated_data[k]
        UserLocation.objects.update_or_create(user=user, defaults=defaults)
        mark_profile_step_completed(user, "location")
        _sync_registration_done(user)
        _log_admin_profile_section(request, user, "location")
        loc = UserLocation.objects.filter(user=user).select_related("country", "state", "district", "city").first()
        data = LocationDetailsReadSerializer(loc).data if loc else empty_location_details_read_data()
        return Response({"success": True, "data": data})


class AdminProfileReligionSectionView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminUser]
    parser_classes = [JSONParser]

    def patch(self, request, matri_id):
        user, err = _target_member(matri_id)
        if err:
            return err
        ser = ReligionDetailsUpdateSerializer(data=request.data, partial=True)
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
        if "partner_caste_preference" in vd:
            defaults["partner_caste_preference"] = vd["partner_caste_preference"]
        UserReligion.objects.update_or_create(user=user, defaults=defaults)
        mark_profile_step_completed(user, "religion")
        _sync_registration_done(user)
        _log_admin_profile_section(request, user, "religion")
        rel = UserReligion.objects.filter(user=user).select_related("religion", "caste_fk", "mother_tongue").first()
        data = ReligionDetailsReadSerializer(rel).data if rel else empty_religion_details_read_data()
        return Response({"success": True, "data": data})


class AdminProfilePersonalSectionView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminUser]
    parser_classes = [JSONParser]

    def patch(self, request, matri_id):
        user, err = _target_member(matri_id)
        if err:
            return err
        ser = PersonalDetailsUpdateSerializer(data=request.data, partial=True)
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
        mark_profile_step_completed(user, "personal")
        _sync_registration_done(user)
        _log_admin_profile_section(request, user, "personal")
        pers = UserPersonal.objects.filter(user=user).select_related("marital_status", "height").first()
        return Response({"success": True, "data": PersonalDetailsReadSerializer(pers).data})


class AdminProfileEducationSectionView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminUser]
    parser_classes = [JSONParser]

    def patch(self, request, matri_id):
        user, err = _target_member(matri_id)
        if err:
            return err
        ser = EducationDetailsUpdateSerializer(
            data=request.data, partial=True, context={"request": request, "user": user}
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
        mark_profile_step_completed(user, "education")
        _sync_registration_done(user)
        _log_admin_profile_section(request, user, "education")
        edu = UserEducation.objects.filter(user=user).select_related(
            "highest_education", "education_subject", "occupation", "annual_income"
        ).first()
        data = EducationDetailsReadSerializer(edu).data if edu else empty_education_details_read_data()
        return Response({"success": True, "data": data})


class AdminProfileAboutSectionView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminUser]
    parser_classes = [JSONParser]

    def patch(self, request, matri_id):
        user, err = _target_member(matri_id)
        if err:
            return err
        ser = AboutDetailsUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={})
        if "about_me" in ser.validated_data:
            profile.about_me = ser.validated_data["about_me"]
        profile.save(update_fields=["about_me", "updated_at"])
        mark_profile_step_completed(user, "about")
        _sync_registration_done(user)
        _log_admin_profile_section(request, user, "about me")
        return Response({"success": True, "data": {"about_me": profile.about_me}})


class AdminProfilePhotosSectionView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminUser]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def patch(self, request, matri_id):
        user, err = _target_member(matri_id)
        if err:
            return err
        try:
            data, files = parse_request_data_and_files(request)
        except ValueError as exc:
            return Response(
                {"success": False, "error": {"code": 400, "message": str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        photos, _ = UserPhotos.objects.get_or_create(user=user, defaults={})
        ser = UserPhotosSerializer(
            photos,
            data=data,
            partial=True,
            context={"request": request, "target_user": user},
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        save_profile_uploads(user, files)
        mark_profile_step_completed(user, "photos")
        _sync_registration_done(user)
        _log_admin_profile_section(request, user, "photos")
        photos = UserPhotos.objects.filter(user=user).first()
        return Response(
            {
                "success": True,
                "data": PhotosDetailsReadSerializer(photos, context={"request": request}).data
                if photos
                else {
                    "profile_photo": None,
                    "full_photo": None,
                    "selfie_photo": None,
                    "family_photo": None,
                    "aadhaar_front": None,
                    "aadhaar_back": None,
                },
            }
        )
