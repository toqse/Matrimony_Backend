from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.my_profiles.models import EmailTemplate
from admin_panel.my_profiles.views import (
    _active_subscription_q,
    _completion_steps,
    _completeness_percent,
    _my_profiles_base_queryset,
    _subscription_label,
    _wishlist_actor_for_panel_user,
)
from admin_panel.profile_admin.patch_helpers import SECTION_HANDLERS
from admin_panel.staff_dashboard.services import staff_profile_for_dashboard
from admin_panel.staff_profiles.registration import (
    _first_drf_error,
    create_user_and_profile_sections,
    parse_request_data_and_files,
    save_profile_uploads,
    validate_core_create_fields,
)
from admin_panel.subscriptions.models import CustomerStaffAssignment
from master.models import Branch as MasterBranch
from profiles.utils import get_profile_completion_data
from profiles.models import UserPhotos, UserProfile
from profiles.views import _build_profile_data_for_user
from wishlist.models import Wishlist

from admin_panel.profile_admin.serializers import _age_from_dob

VALID_FILTERS = frozenset(
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

INVALID_FILTER_MSG = (
    "Invalid filter. Must be: all, incomplete, complete, subscribed, "
    "unsubscribed, verified, unverified."
)
NOT_IN_SCOPE_MSG = "Profile not found or not assigned to you."
VERIFY_FORBIDDEN_MSG = "Profile verification requires Branch Manager or Admin role."
DELETE_FORBIDDEN_MSG = "Profile deletion requires Admin role."


def _resolve_staff_panel(request):
    user = request.user
    if getattr(user, "role", None) != AdminUser.ROLE_STAFF:
        return None, Response(
            {
                "success": False,
                "error": {"code": 403, "message": "Access denied. Staff token required."},
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    if not getattr(user, "is_active", True):
        return None, Response(
            {
                "success": False,
                "error": {"code": 403, "message": "Your account has been deactivated. Contact admin."},
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    staff = staff_profile_for_dashboard(user)
    if not staff:
        return None, Response(
            {
                "success": False,
                "error": {"code": 400, "message": "Staff profile not configured. Contact admin."},
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not staff.is_active:
        return None, Response(
            {
                "success": False,
                "error": {"code": 403, "message": "Your account has been deactivated. Contact admin."},
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return staff, None


def _scoped_staff_profiles_qs(staff):
    user_ids = CustomerStaffAssignment.objects.filter(staff=staff).values_list("user_id", flat=True)
    return _my_profiles_base_queryset().filter(id__in=user_ids)


def _get_user_by_matri(matri_id: str):
    return User.objects.filter(matri_id__iexact=(matri_id or "").strip(), role="user").first()


def _can_access_staff_profile(staff, target: User) -> bool:
    if not target:
        return False
    return CustomerStaffAssignment.objects.filter(user=target, staff=staff).exists()


def _resolve_user_for_staff_or_error(request, staff, matri_id: str):
    user = _get_user_by_matri(matri_id)
    if not user or not _can_access_staff_profile(staff, user):
        return None, Response(
            {"success": False, "error": {"code": 404, "message": NOT_IN_SCOPE_MSG}},
            status=status.HTTP_404_NOT_FOUND,
        )
    return user, None


def _apply_staff_list_filter(qs, filter_value: str):
    f = (filter_value or "all").strip().lower()
    if f not in VALID_FILTERS:
        return None, INVALID_FILTER_MSG
    if f == "verified":
        return qs.filter(user_profile__admin_verified=True), None
    if f == "unverified":
        return qs.filter(Q(user_profile__isnull=True) | Q(user_profile__admin_verified=False)), None
    if f == "subscribed":
        return qs.filter(_active_subscription_q()), None
    if f == "unsubscribed":
        return qs.exclude(_active_subscription_q()), None
    return qs, None


def _build_staff_list_row(request, user: User, wishlist_user_ids=None) -> dict:
    rel = getattr(user, "user_religion", None)
    photos = getattr(user, "user_photos", None)
    religion_name = rel.religion.name if rel and rel.religion_id else None
    caste_name = None
    if rel:
        if rel.caste_fk_id:
            caste_name = rel.caste_fk.name or None
        elif rel.caste:
            caste_name = rel.caste

    matri_id = user.matri_id or ""
    completeness = _completeness_percent(user)
    detail_url = request.build_absolute_uri(
        reverse("staff-my-profiles-detail", kwargs={"matri_id": matri_id})
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
                reverse("staff-my-profiles-refresh", kwargs={"matri_id": matri_id})
            ),
            "wishlist": request.build_absolute_uri(
                reverse("staff-my-profiles-wishlist", kwargs={"matri_id": matri_id})
            ),
            "send_email": request.build_absolute_uri(
                reverse("staff-my-profiles-send-email", kwargs={"matri_id": matri_id})
            ),
            "documents": request.build_absolute_uri(
                reverse("staff-my-profiles-documents", kwargs={"matri_id": matri_id})
            ),
        },
    }


def _master_branch_pk_for_staff(staff):
    if not staff.branch_id:
        return None
    return MasterBranch.objects.filter(code=staff.branch.code).values_list("pk", flat=True).first()


class StaffMyProfilesSummaryView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        staff, err = _resolve_staff_panel(request)
        if err:
            return err
        qs = _scoped_staff_profiles_qs(staff)
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


class StaffMyProfilesListView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        staff, err = _resolve_staff_panel(request)
        if err:
            return err
        qs = _scoped_staff_profiles_qs(staff)

        filter_by = request.query_params.get("filter", "all")
        qs, ferr = _apply_staff_list_filter(qs, filter_by)
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

        rows = [_build_staff_list_row(request, u, wishlist_user_ids) for u in qs.order_by("-created_at")]
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


class StaffMyProfilesDetailView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request, matri_id):
        staff, err = _resolve_staff_panel(request)
        if err:
            return err
        user, uerr = _resolve_user_for_staff_or_error(request, staff, matri_id)
        if uerr:
            return uerr
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
        staff, err = _resolve_staff_panel(request)
        if err:
            return err
        user, uerr = _resolve_user_for_staff_or_error(request, staff, matri_id)
        if uerr:
            return uerr
        try:
            data, files = parse_request_data_and_files(request)
        except ValueError as exc:
            return Response(
                {"success": False, "error": {"code": 400, "message": str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if "admin_verified" in data:
            return Response(
                {"success": False, "error": {"code": 403, "message": VERIFY_FORBIDDEN_MSG}},
                status=status.HTTP_403_FORBIDDEN,
            )
        if getattr(user, "is_blocked", False):
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Cannot edit a blocked profile. Contact admin."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if "has_horoscope" in data:
            profile.has_horoscope = bool(data["has_horoscope"])
            profile.save(update_fields=["has_horoscope", "updated_at"])
        for key, handler in SECTION_HANDLERS.items():
            if key not in data:
                continue
            payload = data[key]
            if payload is None:
                continue
            if key == "about_me":
                if isinstance(payload, str):
                    if len(payload) > 500:
                        return Response(
                            {
                                "success": False,
                                "error": {"code": 400, "message": "About me must be 500 characters or fewer."},
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    try:
                        handler(user, {"about_me": payload})
                    except DRFValidationError as e:
                        return Response(
                            {
                                "success": False,
                                "error": {"code": 400, "message": _first_drf_error(e)},
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                else:
                    if isinstance(payload, dict):
                        t = payload.get("about_me") or ""
                        if len(t) > 500:
                            return Response(
                                {
                                    "success": False,
                                    "error": {"code": 400, "message": "About me must be 500 characters or fewer."},
                                },
                                status=status.HTTP_400_BAD_REQUEST,
                            )
                    try:
                        handler(user, payload)
                    except DRFValidationError as e:
                        return Response(
                            {
                                "success": False,
                                "error": {"code": 400, "message": _first_drf_error(e)},
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
            else:
                try:
                    handler(user, payload)
                except DRFValidationError as e:
                    return Response(
                        {
                            "success": False,
                            "error": {"code": 400, "message": _first_drf_error(e)},
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        save_profile_uploads(user, files)
        completion = get_profile_completion_data(user)
        user.is_registration_profile_completed = completion["profile_status"] == "completed"
        user.save(update_fields=["is_registration_profile_completed", "updated_at"])
        payload = _build_profile_data_for_user(user, request, include_contact=True, include_family=True)
        return Response({"success": True, "message": "Profile updated successfully.", "data": payload})

    def delete(self, request, matri_id):
        staff, err = _resolve_staff_panel(request)
        if err:
            return err
        _, uerr = _resolve_user_for_staff_or_error(request, staff, matri_id)
        if uerr:
            return uerr
        return Response(
            {"success": False, "error": {"code": 403, "message": DELETE_FORBIDDEN_MSG}},
            status=status.HTTP_403_FORBIDDEN,
        )


class StaffMyProfilesRefreshView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, matri_id):
        staff, err = _resolve_staff_panel(request)
        if err:
            return err
        user, uerr = _resolve_user_for_staff_or_error(request, staff, matri_id)
        if uerr:
            return uerr
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


class StaffMyProfilesWishlistView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, matri_id):
        staff, err = _resolve_staff_panel(request)
        if err:
            return err
        user, uerr = _resolve_user_for_staff_or_error(request, staff, matri_id)
        if uerr:
            return uerr
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


class StaffMyProfilesDocumentsView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, matri_id):
        staff, err = _resolve_staff_panel(request)
        if err:
            return err
        user, uerr = _resolve_user_for_staff_or_error(request, staff, matri_id)
        if uerr:
            return uerr
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


class StaffMyProfilesSendEmailView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, matri_id):
        staff, err = _resolve_staff_panel(request)
        if err:
            return err
        user, uerr = _resolve_user_for_staff_or_error(request, staff, matri_id)
        if uerr:
            return uerr
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


class StaffMyProfilesCreateView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def post(self, request):
        staff, err = _resolve_staff_panel(request)
        if err:
            return err

        try:
            data, files = parse_request_data_and_files(request)
        except ValueError as exc:
            return Response(
                {"success": False, "error": {"code": 400, "message": str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        errors, norm = validate_core_create_fields(data)
        if errors:
            first = next(iter(errors))
            return Response(
                {"success": False, "error": {"code": 400, "message": errors[first], "details": errors}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        branch_pk = _master_branch_pk_for_staff(staff)
        if not branch_pk:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Staff branch could not be resolved. Contact admin."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = create_user_and_profile_sections(
                name=norm["name"],
                mobile=norm["mobile"],
                gender=norm["gender"],
                dob_iso=norm["dob_iso"],
                email=norm["email"],
                branch_pk=branch_pk,
                data=data,
                files=files,
                staff=staff,
            )
        except DRFValidationError as exc:
            return Response(
                {"success": False, "error": {"code": 400, "message": _first_drf_error(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {"success": False, "error": {"code": 400, "message": str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "success": True,
                "message": f"Profile created successfully. Matri ID: {user.matri_id}.",
                "data": {
                    "matri_id": user.matri_id,
                    "name": user.name,
                    "phone": user.phone_number,
                    "profile_completion_percentage": get_profile_completion_data(user)[
                        "profile_completion_percentage"
                    ],
                },
            },
            status=status.HTTP_201_CREATED,
        )
