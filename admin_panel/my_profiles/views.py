from __future__ import annotations

import re
from datetime import datetime

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.bulk_upload.services import import_profile_row, mobile_exists_in_db, normalize_mobile
from admin_panel.commissions.views import _branch_manager_code_or_error
from admin_panel.permissions import IsBranchManager
from admin_panel.profile_admin.patch_helpers import SECTION_HANDLERS
from admin_panel.subscriptions.models import CustomerStaffAssignment
from master.models import Branch as MasterBranch
from profiles.models import UserPhotos, UserProfile
from profiles.views import _build_profile_data_for_user
from wishlist.models import Wishlist

from .models import EmailTemplate


VALID_FILTERS = [
    "all",
    "incomplete",
    "complete",
    "subscribed",
    "unsubscribed",
    "verified",
    "unverified",
]


def _manager_branch_code(user):
    return (
        MasterBranch.objects.filter(pk=getattr(user, "branch_id", None))
        .values_list("code", flat=True)
        .first()
    )


def _get_user_by_matri(matri_id: str):
    return User.objects.filter(matri_id__iexact=(matri_id or "").strip(), role="user").first()


def _my_profiles_base_queryset():
    return (
        User.objects.filter(role="user", is_active=True)
        .select_related(
            "branch",
            "user_plan__plan",
            "user_profile",
            "user_religion__religion",
            "user_religion__caste_fk",
            "user_location",
            "user_personal",
            "user_education",
            "user_photos",
            "staff_assignment__staff__branch",
        )
        .distinct()
    )


def _scoped_my_profiles_qs(request):
    code, err = _branch_manager_code_or_error(request)
    if err:
        return None, err
    qs = _my_profiles_base_queryset().filter(
        Q(branch__code=code) | Q(staff_assignment__staff__branch__code=code)
    )
    return qs, None


def _can_access_my_profile(request, target: User) -> bool:
    code = _manager_branch_code(request.user)
    if not code:
        return False
    if target.branch_id and target.branch and target.branch.code == code:
        return True
    return CustomerStaffAssignment.objects.filter(
        user=target, staff__branch__code=code
    ).exists()


def _active_subscription_q():
    today = timezone.localdate()
    return Q(user_plan__is_active=True) & (
        Q(user_plan__valid_until__isnull=True) | Q(user_plan__valid_until__gte=today)
    )


def _completion_steps(user: User):
    profile = getattr(user, "user_profile", None)
    photos = getattr(user, "user_photos", None)
    return {
        "location": hasattr(user, "user_location"),
        "religion": hasattr(user, "user_religion"),
        "personal": hasattr(user, "user_personal"),
        "education": hasattr(user, "user_education"),
        "about_me": bool((getattr(profile, "about_me", "") or "").strip()) if profile else False,
        "photos": bool(getattr(photos, "profile_photo", None)) if photos else False,
    }


def _completeness_percent(user: User) -> int:
    done = sum(1 for v in _completion_steps(user).values() if v)
    return int((done / 6) * 100)


def _resolve_user_or_error(request, matri_id: str):
    user = _get_user_by_matri(matri_id)
    if not user or not _can_access_my_profile(request, user):
        return None, Response(
            {
                "success": False,
                "error": {"code": 404, "message": "Profile not found or not in your branch."},
            },
            status=status.HTTP_404_NOT_FOUND,
        )
    return user, None


def _subscription_label(user: User) -> str:
    up = getattr(user, "user_plan", None)
    if up and up.plan_id and up.is_active and (up.valid_until is None or up.valid_until >= timezone.localdate()):
        return up.plan.name or "None"
    return "None"


def _wishlist_actor_for_panel_user(panel_user: AdminUser):
    mobile = (getattr(panel_user, "mobile", "") or "").strip()
    normalized = normalize_mobile(mobile)
    if not normalized:
        return None
    digits = normalized[-10:]
    return User.objects.filter(
        Q(mobile=normalized) | Q(mobile=f"91{digits}") | Q(mobile=digits)
    ).first()


def _build_list_row(request, user: User, wishlist_user_ids=None) -> dict:
    rel = getattr(user, "user_religion", None)
    photos = getattr(user, "user_photos", None)
    religion_name = rel.religion.name if rel and rel.religion_id else None
    caste_name = None
    if rel:
        if rel.caste_fk_id:
            caste_name = rel.caste_fk.name or None
        elif rel.caste:
            caste_name = rel.caste

    from admin_panel.profile_admin.serializers import _age_from_dob

    matri_id = user.matri_id or ""
    completeness = _completeness_percent(user)
    detail_url = request.build_absolute_uri(
        reverse("my-profiles-detail", kwargs={"matri_id": matri_id})
    )
    profile_photo = None
    if photos and photos.profile_photo and getattr(photos.profile_photo, "url", None):
        profile_photo = request.build_absolute_uri(photos.profile_photo.url)

    return {
        "matri_id": matri_id,
        "name": user.name or "",
        "gender": user.get_gender_display() if user.gender else "",
        "age": _age_from_dob(user.dob),
        "religion": religion_name,
        "caste": caste_name,
        "subscription_plan": _subscription_label(user),
        "is_verified": bool(getattr(getattr(user, "user_profile", None), "admin_verified", False)),
        "completeness": completeness,
        "profile_status": "complete" if completeness == 100 else "incomplete",
        "is_wishlisted": bool(wishlist_user_ids and user.id in wishlist_user_ids),
        "profile_photo": profile_photo,
        "quick_actions": {
            "edit": detail_url,
            "view": detail_url,
            "refresh": request.build_absolute_uri(
                reverse("my-profiles-refresh", kwargs={"matri_id": matri_id})
            ),
            "wishlist": request.build_absolute_uri(
                reverse("my-profiles-wishlist", kwargs={"matri_id": matri_id})
            ),
            "send_email": request.build_absolute_uri(
                reverse("my-profiles-send-email", kwargs={"matri_id": matri_id})
            ),
            "documents": request.build_absolute_uri(
                reverse("my-profiles-documents", kwargs={"matri_id": matri_id})
            ),
        },
    }


def _apply_list_filter(qs, filter_value: str):
    f = (filter_value or "all").strip().lower()
    if f not in VALID_FILTERS:
        return None, (
            "Invalid filter. Must be one of: all, incomplete, complete, "
            "subscribed, unsubscribed, verified, unverified."
        )
    if f == "verified":
        return qs.filter(user_profile__admin_verified=True), None
    if f == "unverified":
        return qs.filter(Q(user_profile__isnull=True) | Q(user_profile__admin_verified=False)), None
    if f == "subscribed":
        return qs.filter(_active_subscription_q()), None
    if f == "unsubscribed":
        return qs.exclude(_active_subscription_q()), None
    return qs, None


class MyProfilesSummaryView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManager]

    def get(self, request):
        qs, err = _scoped_my_profiles_qs(request)
        if err:
            return err
        total = qs.count()
        verified = qs.filter(user_profile__admin_verified=True).count()
        unverified = total - verified
        subscribed = qs.filter(_active_subscription_q()).count()
        incomplete_count = sum(1 for u in qs if _completeness_percent(u) < 100)
        return Response(
            {
                "success": True,
                "data": {
                    "total_profiles": total,
                    "verified": verified,
                    "unverified": unverified,
                    "subscribed": subscribed,
                    "incomplete_count": incomplete_count,
                    "incomplete_message": (
                        f"{incomplete_count} profile(s) with incomplete data need attention"
                        if incomplete_count > 0
                        else None
                    ),
                },
            }
        )


class MyProfilesListView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManager]

    def get(self, request):
        qs, err = _scoped_my_profiles_qs(request)
        if err:
            return err

        filter_by = request.query_params.get("filter", "all")
        qs, ferr = _apply_list_filter(qs, filter_by)
        if ferr:
            return Response(
                {"success": False, "error": {"code": 400, "message": ferr}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(matri_id__icontains=search))

        wishlist_actor = _wishlist_actor_for_panel_user(request.user)
        wishlist_user_ids = set()
        if wishlist_actor:
            wishlist_user_ids = set(
                Wishlist.objects.filter(user=wishlist_actor).values_list("profile_id", flat=True)
            )

        rows = [_build_list_row(request, u, wishlist_user_ids) for u in qs.order_by("-created_at")]
        if filter_by == "complete":
            rows = [r for r in rows if r["completeness"] == 100]
        elif filter_by == "incomplete":
            rows = [r for r in rows if r["completeness"] < 100]

        page_size = min(max(int(request.query_params.get("page_size", 20)), 1), 100)
        page_num = max(int(request.query_params.get("page", 1)), 1)
        start = (page_num - 1) * page_size
        end = start + page_size
        total = len(rows)
        page_rows = rows[start:end]

        next_link = None
        previous_link = None
        if end < total:
            next_link = f"?page={page_num + 1}&page_size={page_size}"
        if page_num > 1:
            previous_link = f"?page={page_num - 1}&page_size={page_size}"

        return Response(
            {
                "success": True,
                "data": {
                    "count": total,
                    "page": page_num,
                    "page_size": page_size,
                    "next": next_link,
                    "previous": previous_link,
                    "results": page_rows,
                },
            }
        )


class MyProfilesDetailView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManager]

    def get(self, request, matri_id):
        user, err = _resolve_user_or_error(request, matri_id)
        if err:
            return err
        data = _build_profile_data_for_user(user, request, include_contact=True, include_family=True)
        completeness = _completeness_percent(user)
        profile = getattr(user, "user_profile", None) or UserProfile.objects.filter(user=user).first()
        data["admin"] = {
            "admin_verified": bool(profile and profile.admin_verified),
            "has_horoscope": bool(profile and profile.has_horoscope),
            "is_blocked": getattr(user, "is_blocked", False),
            "profile_status": "complete" if completeness == 100 else "incomplete",
            "profile_completion_percentage": completeness,
        }
        return Response({"success": True, "data": data})

    def patch(self, request, matri_id):
        user, err = _resolve_user_or_error(request, matri_id)
        if err:
            return err
        if getattr(user, "is_blocked", False):
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Cannot edit a blocked profile. Contact admin."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if "admin_verified" in request.data:
            profile.admin_verified = bool(request.data["admin_verified"])
            profile.save(update_fields=["admin_verified", "updated_at"])
        if "has_horoscope" in request.data:
            profile.has_horoscope = bool(request.data["has_horoscope"])
            profile.save(update_fields=["has_horoscope", "updated_at"])
        for key, handler in SECTION_HANDLERS.items():
            if key not in request.data:
                continue
            payload = request.data[key]
            if payload is None:
                continue
            if key == "about_me" and isinstance(payload, str):
                handler(user, {"about_me": payload})
            else:
                handler(user, payload)
        data = _build_profile_data_for_user(user, request, include_contact=True, include_family=True)
        return Response({"success": True, "message": "Profile updated successfully.", "data": data})


class MyProfilesVerifyView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManager]

    def patch(self, request, matri_id):
        user, err = _resolve_user_or_error(request, matri_id)
        if err:
            return err
        profile, _ = UserProfile.objects.get_or_create(user=user)
        completeness = _completeness_percent(user)
        next_v = not profile.admin_verified
        if next_v and completeness < 100:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": 400,
                        "message": (
                            "Cannot verify an incomplete profile. "
                            f"Profile is {completeness}% complete. "
                            "All sections must be filled before verification."
                        ),
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile.admin_verified = next_v
        profile.save(update_fields=["admin_verified", "updated_at"])
        status_text = "verified" if profile.admin_verified else "unverified"
        return Response(
            {
                "success": True,
                "message": f"Profile {matri_id} marked as {status_text}.",
                "data": {"matri_id": matri_id, "is_verified": profile.admin_verified},
            }
        )


class MyProfilesRefreshView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManager]

    def patch(self, request, matri_id):
        user, err = _resolve_user_or_error(request, matri_id)
        if err:
            return err
        completeness = _completeness_percent(user)
        steps = _completion_steps(user)
        return Response(
            {
                "success": True,
                "data": {
                    "matri_id": matri_id,
                    "completeness": completeness,
                    "profile_status": "complete" if completeness == 100 else "incomplete",
                    "steps_remaining": [k for k, done in steps.items() if not done],
                },
            }
        )


class MyProfilesWishlistView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManager]

    def post(self, request, matri_id):
        user, err = _resolve_user_or_error(request, matri_id)
        if err:
            return err
        actor = _wishlist_actor_for_panel_user(request.user)
        if not actor:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "No linked user account found to manage wishlist."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        wl, created = Wishlist.objects.get_or_create(user=actor, profile=user)
        if not created:
            wl.delete()
            return Response(
                {
                    "success": True,
                    "data": {"is_wishlisted": False},
                    "message": "Removed from wishlist.",
                }
            )
        return Response(
            {
                "success": True,
                "data": {"is_wishlisted": True},
                "message": "Added to wishlist.",
            }
        )


class MyProfilesDocumentsView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManager]

    def get(self, request, matri_id):
        user, err = _resolve_user_or_error(request, matri_id)
        if err:
            return err
        photos = getattr(user, "user_photos", None) or UserPhotos.objects.filter(user=user).first()

        def abs_url(field_name):
            if not photos:
                return None
            f = getattr(photos, field_name, None)
            if f and getattr(f, "url", None):
                return request.build_absolute_uri(f.url)
            return None

        docs = {
            "profile_photo": abs_url("profile_photo"),
            "full_photo": abs_url("full_photo"),
            "selfie_photo": abs_url("selfie_photo"),
            "family_photo": abs_url("family_photo"),
            "aadhaar_front": abs_url("aadhaar_front"),
            "aadhaar_back": abs_url("aadhaar_back"),
        }
        uploaded = {k: v for k, v in docs.items() if v}
        return Response(
            {
                "success": True,
                "data": {
                    "matri_id": matri_id,
                    "documents": docs,
                    "uploaded_count": len(uploaded),
                    "missing": [k for k, v in docs.items() if not v],
                },
            }
        )


class MyProfilesSendEmailView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManager]

    def post(self, request, matri_id):
        user, err = _resolve_user_or_error(request, matri_id)
        if err:
            return err
        if not user.email:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "This profile has no registered email address."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        template_id = request.data.get("template_id")
        if not template_id:
            return Response(
                {"success": False, "error": {"code": 400, "message": "template_id is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        template = EmailTemplate.objects.filter(id=template_id).first()
        if not template:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Email template not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not template.is_active:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Email template is inactive. Activate it first."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        subject = (template.subject or "").replace("{name}", user.name or "").replace(
            "{matri_id}", user.matri_id or ""
        )
        body = (template.body_text or "").replace("{name}", user.name or "").replace(
            "{matri_id}", user.matri_id or ""
        )
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return Response({"success": True, "message": f"Email sent successfully to {user.email}."})


class MyProfilesCreateView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsBranchManager]

    def post(self, request):
        _, err = _branch_manager_code_or_error(request)
        if err:
            return err
        if not getattr(request.user, "branch_id", None):
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "No branch assigned to your account. Contact admin."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = request.data
        errors = {}
        name = (data.get("name") or "").strip()
        if not name:
            errors["name"] = "Name is required."

        phone = (data.get("phone_number") or data.get("phone") or data.get("mobile") or "").strip()
        if not phone:
            errors["phone_number"] = "Phone number is required."
            mobile = None
        else:
            mobile = normalize_mobile(phone)
            if not mobile:
                errors["phone_number"] = "Enter a valid phone number in +91XXXXXXXXXX format."
            elif mobile_exists_in_db(mobile):
                errors["phone_number"] = "Phone number already registered."

        gender = (data.get("gender") or "").strip().upper()
        if not gender:
            errors["gender"] = "Gender is required."
        elif gender not in {"M", "F", "O"}:
            errors["gender"] = "Gender must be M, F, or O."

        dob = (data.get("dob") or "").strip()
        if not dob:
            errors["dob"] = "Date of birth is required."
            dob_iso = None
        elif not re.match(r"^\d{2}-\d{2}-\d{4}$", dob):
            errors["dob"] = "Invalid date format. Use DD-MM-YYYY."
            dob_iso = None
        else:
            try:
                dob_iso = datetime.strptime(dob, "%d-%m-%Y").date().isoformat()
            except ValueError:
                errors["dob"] = "Invalid date format. Use DD-MM-YYYY."
                dob_iso = None

        email = (data.get("email") or "").strip()
        if email:
            from django.core.exceptions import ValidationError
            from django.core.validators import validate_email
            try:
                validate_email(email)
            except ValidationError:
                errors["email"] = "Invalid email address."

        if errors:
            first = next(iter(errors))
            return Response(
                {"success": False, "error": {"code": 400, "message": errors[first], "details": errors}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = dict(data)
        payload["name"] = name
        payload["mobile"] = mobile
        payload["gender"] = gender
        payload["dob"] = dob_iso
        if email:
            payload["email"] = email

        try:
            with transaction.atomic():
                import_profile_row(payload, request.user.branch_id)
        except Exception as exc:
            return Response(
                {"success": False, "error": {"code": 400, "message": str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        digits = mobile[-10:]
        user = User.objects.filter(
            Q(mobile=mobile) | Q(mobile=f"91{digits}") | Q(mobile=digits)
        ).order_by("-created_at").first()
        if not user:
            return Response(
                {"success": False, "error": {"code": 500, "message": "Profile created but user not found"}},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(
            {
                "success": True,
                "message": f"Profile created successfully. Matri ID: {user.matri_id}.",
                "data": {"matri_id": user.matri_id, "name": user.name, "phone": user.phone_number},
            },
            status=status.HTTP_201_CREATED,
        )
