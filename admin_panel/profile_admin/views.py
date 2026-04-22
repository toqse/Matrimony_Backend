from __future__ import annotations

import uuid

from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.staff_mgmt.models import StaffProfile
from admin_panel.subscriptions.models import CustomerStaffAssignment
from master.models import Branch as MasterBranch
from profiles.models import UserProfile
from profiles.utils import get_profile_completion_data
from profiles.views import _build_profile_data_for_user

from admin_panel.audit_log.mixins import AuditLogMixin
from admin_panel.audit_log.models import AuditLog
from admin_panel.audit_log.utils import create_audit_log

from admin_panel.staff_profiles.registration import (
    _first_drf_error,
    apply_profile_sections,
    parse_request_data_and_files,
    save_profile_uploads,
)

from .merge_service import merge_user_accounts
from .serializers import AdminProfileListSerializer, _age_from_dob

STAFF_VERIFY_FORBIDDEN_MSG = "Profile verification requires Branch Manager or Admin role."
STAFF_DELETE_FORBIDDEN_MSG = "Profile deletion requires Admin role."


def _staff_profile_for_admin_user(user):
    mobile = (getattr(user, "mobile", "") or "").strip()
    mobile10 = mobile[-10:] if mobile.startswith("+91") else mobile
    return StaffProfile.objects.filter(mobile=mobile10, is_deleted=False).first()


def _manager_branch_code(user):
    return (
        MasterBranch.objects.filter(pk=getattr(user, "branch_id", None))
        .values_list("code", flat=True)
        .first()
    )


def _get_user_by_matri(matri_id: str):
    return User.objects.filter(matri_id__iexact=(matri_id or "").strip()).first()


def _can_access_profile(request, target: User) -> bool:
    role = getattr(request.user, "role", None)
    if role == AdminUser.ROLE_ADMIN:
        return True
    if role == AdminUser.ROLE_BRANCH_MANAGER:
        code = _manager_branch_code(request.user)
        if not code:
            return False
        ub = target.branch
        if ub and ub.code == code:
            return True
        # Also allow customers already linked to staff in manager's branch.
        return CustomerStaffAssignment.objects.filter(
            user=target, staff__branch__code=code, staff__is_deleted=False
        ).exists()
    if role == AdminUser.ROLE_STAFF:
        sp = _staff_profile_for_admin_user(request.user)
        if not sp:
            return False
        return CustomerStaffAssignment.objects.filter(user=target, staff=sp).exists()
    return False


def _can_edit(request, target: User) -> bool:
    return _can_access_profile(request, target)


def _can_delete(request) -> bool:
    return getattr(request.user, "role", None) == AdminUser.ROLE_ADMIN


def _completion_percent_from_profile(profile) -> int:
    """Match get_profile_completion % without DB hits (list view uses prefetched user_profile)."""
    if profile is None:
        return 0
    steps = (
        bool(profile.location_completed),
        bool(profile.religion_completed),
        bool(profile.personal_completed),
        bool(getattr(profile, "family_completed", False)),
        bool(profile.education_completed),
        bool(profile.about_completed),
        bool(profile.photos_completed),
    )
    n = len(steps)
    return int((sum(steps) / n) * 100) if n else 0


def _build_list_row(user: User) -> dict:
    rel = getattr(user, "user_religion", None)
    pers = getattr(user, "user_personal", None)
    plan_name = ""
    up = getattr(user, "user_plan", None)
    if up and up.plan_id:
        plan_name = up.plan.name or ""
    staff_name = None
    asn = getattr(user, "staff_assignment", None)
    if asn and asn.staff:
        staff_name = asn.staff.name
    profile = getattr(user, "user_profile", None)
    religion_name = rel.religion.name if rel and rel.religion_id else ""
    caste_name = ""
    if rel:
        if rel.caste_fk_id:
            caste_name = rel.caste_fk.name or ""
        elif rel.caste:
            caste_name = rel.caste
    marital = pers.marital_status.name if pers and pers.marital_status_id else ""
    gender_display = user.get_gender_display() if user.gender else ""
    return {
        "matri_id": user.matri_id or "",
        "name": user.name or "",
        "gender": gender_display,
        "age": _age_from_dob(user.dob),
        "religion": religion_name,
        "caste": caste_name,
        "marital_status": marital,
        "plan": plan_name,
        "assigned_staff": staff_name,
        "verified": bool(profile and profile.admin_verified),
        "completion_percent": _completion_percent_from_profile(profile),
        "horoscope_available": bool(profile and profile.has_horoscope),
        "is_active": user.is_active,
        "is_blocked": getattr(user, "is_blocked", False),
    }


class AdminProfileListAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            # Use admin panel standard pagination (supports page_size param).
            from admin_panel.pagination import StandardPagination

            self._paginator = StandardPagination()
        return self._paginator

    def paginate_queryset(self, queryset, request):
        if self.paginator is None:
            return None
        return self.paginator.paginate_queryset(queryset, request, view=self)

    def get(self, request):
        qs = User.objects.filter(role="user").select_related(
            "branch",
            "user_plan__plan",
            "user_profile",
            "user_religion__religion",
            "user_religion__caste_fk",
            "user_personal__marital_status",
            "staff_assignment__staff",
        )

        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(matri_id__icontains=search))

        gender = (request.query_params.get("gender") or "").strip().upper()
        if gender in {"M", "F", "O"}:
            qs = qs.filter(gender=gender)

        religion_id = request.query_params.get("religion_id")
        if religion_id:
            qs = qs.filter(user_religion__religion_id=religion_id)

        plan = (request.query_params.get("plan") or "").strip()
        if plan.isdigit():
            qs = qs.filter(user_plan__plan_id=int(plan))
        elif plan:
            qs = qs.filter(user_plan__plan__name__iexact=plan)

        verified = (request.query_params.get("verified") or "").strip().lower()
        if verified in {"true", "1", "yes"}:
            qs = qs.filter(user_profile__admin_verified=True)
        elif verified in {"false", "0", "no"}:
            qs = qs.filter(Q(user_profile__admin_verified=False) | Q(user_profile__isnull=True))

        staff_id = request.query_params.get("staff_id")
        if staff_id:
            qs = qs.filter(staff_assignment__staff_id=staff_id)

        if (request.query_params.get("show_inactive") or "").strip().lower() not in {"1", "true", "yes"}:
            qs = qs.filter(is_active=True)

        role = getattr(request.user, "role", None)
        if role == AdminUser.ROLE_BRANCH_MANAGER:
            code = _manager_branch_code(request.user)
            qs = qs.filter(branch__code=code) if code else qs.none()
        elif role == AdminUser.ROLE_STAFF:
            sp = _staff_profile_for_admin_user(request.user)
            qs = qs.filter(staff_assignment__staff=sp) if sp else qs.none()

        qs = qs.order_by("-created_at")
        page = self.paginate_queryset(qs, request)
        items = page if page is not None else qs[:2000]
        rows = [_build_list_row(u) for u in items]
        ser = AdminProfileListSerializer(rows, many=True)
        if page is not None:
            paged = self.paginator.get_paginated_response(ser.data)
            return Response({"success": True, "data": paged.data})
        return Response({"success": True, "data": {"count": len(rows), "results": ser.data}})


class StaffProfileListAPIView(AdminProfileListAPIView):
    def get(self, request):
        if getattr(request.user, "role", None) != AdminUser.ROLE_STAFF:
            return Response(
                {"success": False, "error": {"code": 403, "message": "Insufficient permissions"}},
                status=403,
            )
        return super().get(request)


class AdminProfileDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request, matri_id):
        user = _get_user_by_matri(matri_id)
        if not user:
            return Response({"success": False, "error": {"code": 404, "message": "Profile not found"}}, status=404)
        if not _can_access_profile(request, user):
            return Response({"success": False, "error": {"code": 403, "message": "Access denied"}}, status=403)
        data = _build_profile_data_for_user(user, request, include_contact=True, include_family=True)
        completion = get_profile_completion_data(user)
        profile = getattr(user, "user_profile", None) or UserProfile.objects.filter(user=user).first()
        data["admin"] = {
            "admin_verified": bool(profile and profile.admin_verified),
            "has_horoscope": bool(profile and profile.has_horoscope),
            "is_blocked": getattr(user, "is_blocked", False),
            "profile_status": completion["profile_status"],
            "profile_completion_percentage": completion["profile_completion_percentage"],
        }
        return Response({"success": True, "data": data})

    def patch(self, request, matri_id):
        user = _get_user_by_matri(matri_id)
        if not user:
            return Response({"success": False, "error": {"code": 404, "message": "Profile not found"}}, status=404)
        if not _can_edit(request, user):
            return Response({"success": False, "error": {"code": 403, "message": "Access denied"}}, status=403)

        try:
            data, files = parse_request_data_and_files(request)
        except ValueError as exc:
            return Response({"success": False, "error": {"code": 400, "message": str(exc)}}, status=400)

        if getattr(request.user, "role", None) == AdminUser.ROLE_STAFF and "admin_verified" in data:
            return Response(
                {"success": False, "error": {"code": 403, "message": STAFF_VERIFY_FORBIDDEN_MSG}},
                status=403,
            )

        profile, _ = UserProfile.objects.get_or_create(user=user)
        try:
            with transaction.atomic():
                if "admin_verified" in data:
                    profile.admin_verified = bool(data["admin_verified"])
                    profile.save(update_fields=["admin_verified", "updated_at"])
                if "has_horoscope" in data:
                    profile.has_horoscope = bool(data["has_horoscope"])
                    profile.save(update_fields=["has_horoscope", "updated_at"])
                apply_profile_sections(user, data)
        except DRFValidationError as exc:
            return Response(
                {"success": False, "error": {"code": 400, "message": _first_drf_error(exc)}},
                status=400,
            )

        save_profile_uploads(user, files)
        completion = get_profile_completion_data(user)
        user.is_registration_profile_completed = completion["profile_status"] == "completed"
        user.save(update_fields=["is_registration_profile_completed", "updated_at"])

        actor_nm = (getattr(request.user, "name", "") or "").strip()
        create_audit_log(
            request,
            action=AuditLog.ACTION_UPDATE_PROFILE,
            resource=f"profile:{user.matri_id}",
            details=f"{actor_nm} updated profile data for {user.name}.",
            target_profile_name=(user.name or "").strip(),
            action_type=AuditLog.ACTION_TYPE_UPDATE_PROFILE,
        )

        data = _build_profile_data_for_user(user, request, include_contact=True, include_family=True)
        p2 = UserProfile.objects.filter(user=user).first()
        data["admin"] = {
            "admin_verified": bool(p2 and p2.admin_verified),
            "has_horoscope": bool(p2 and p2.has_horoscope),
            "is_blocked": getattr(user, "is_blocked", False),
            "profile_status": completion["profile_status"],
            "profile_completion_percentage": completion["profile_completion_percentage"],
        }
        return Response({"success": True, "data": data})

    def delete(self, request, matri_id):
        if getattr(request.user, "role", None) == AdminUser.ROLE_STAFF:
            return Response(
                {"success": False, "error": {"code": 403, "message": STAFF_DELETE_FORBIDDEN_MSG}},
                status=403,
            )
        if not _can_delete(request):
            return Response({"success": False, "error": {"code": 403, "message": "Insufficient permissions"}}, status=403)
        user = _get_user_by_matri(matri_id)
        if not user:
            return Response({"success": False, "error": {"code": 404, "message": "Profile not found"}}, status=404)
        suffix = uuid.uuid4().hex[:10]
        anon = f"del{suffix}"[:20]
        user.mobile = anon
        user.is_active = False
        user.save(update_fields=["mobile", "is_active", "updated_at"])
        actor_nm = (getattr(request.user, "name", "") or "").strip()
        create_audit_log(
            request,
            action=AuditLog.ACTION_DELETE,
            resource=f"profile:{user.matri_id}",
            details=f"{actor_nm} deactivated profile for {user.name}.",
            target_profile_name=(user.name or "").strip(),
            action_type=AuditLog.ACTION_TYPE_UPDATE_PROFILE,
        )
        return Response({"success": True, "data": {"matri_id": user.matri_id, "soft_deleted": True}})


class AdminProfileVerifyAPIView(AuditLogMixin, APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, matri_id):
        user = _get_user_by_matri(matri_id)
        if not user:
            return Response({"success": False, "error": {"code": 404, "message": "Profile not found"}}, status=404)
        if getattr(request.user, "role", None) == AdminUser.ROLE_STAFF:
            return Response(
                {"success": False, "error": {"code": 403, "message": STAFF_VERIFY_FORBIDDEN_MSG}},
                status=403,
            )
        if not _can_edit(request, user):
            return Response({"success": False, "error": {"code": 403, "message": "Access denied"}}, status=403)
        completion = get_profile_completion_data(user)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if request.data.get("verified") is not None:
            next_v = bool(request.data["verified"])
        else:
            next_v = not profile.admin_verified
        if next_v and completion["profile_status"] != "completed":
            return Response(
                {"success": False, "error": {"code": 400, "message": "Cannot verify an incomplete profile"}},
                status=400,
            )
        prev_v = profile.admin_verified
        profile.admin_verified = next_v
        profile.save(update_fields=["admin_verified", "updated_at"])
        actor_nm = (getattr(request.user, "name", "") or "").strip()
        verb = "verified" if profile.admin_verified else "unverified"
        self.log_action(
            action=AuditLog.ACTION_PROFILE_VERIFY if profile.admin_verified else AuditLog.ACTION_PROFILE_UNVERIFY,
            resource=f"profile:{user.matri_id}",
            details=f"{actor_nm} {verb} profile for {user.name}.",
            old_value={"verified": prev_v},
            new_value={"verified": profile.admin_verified},
            target_profile_name=(user.name or "").strip(),
            action_type=AuditLog.ACTION_TYPE_UPDATE_PROFILE,
        )
        return Response(
            {
                "success": True,
                "data": {"matri_id": user.matri_id, "verified": profile.admin_verified},
            }
        )


class AdminProfileAssignStaffAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, matri_id):
        user = _get_user_by_matri(matri_id)
        if not user:
            return Response({"success": False, "error": {"code": 404, "message": "Profile not found"}}, status=404)
        if not _can_edit(request, user):
            return Response({"success": False, "error": {"code": 403, "message": "Access denied"}}, status=403)
        staff_id = request.data.get("staff_id")
        if staff_id is None:
            return Response(
                {"success": False, "error": {"code": 400, "message": "staff_id is required"}},
                status=400,
            )
        try:
            sp = StaffProfile.objects.select_related("branch").get(pk=int(staff_id), is_deleted=False)
        except (StaffProfile.DoesNotExist, ValueError, TypeError):
            return Response(
                {"success": False, "error": {"code": 400, "message": "Staff not found or inactive"}},
                status=400,
            )
        if not sp.is_active:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Staff not found or inactive"}},
                status=400,
            )
        if user.branch_id and sp.branch.code != user.branch.code:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Staff belongs to a different branch"}},
                status=400,
            )
        CustomerStaffAssignment.objects.update_or_create(user=user, defaults={"staff": sp})
        actor_nm = (getattr(request.user, "name", "") or "").strip()
        create_audit_log(
            request,
            action=AuditLog.ACTION_UPDATE_PROFILE,
            resource=f"profile:{user.matri_id}",
            details=f"{actor_nm} assigned staff {sp.name} for {user.name}.",
            target_profile_name=(user.name or "").strip(),
            action_type=AuditLog.ACTION_TYPE_UPDATE_PROFILE,
        )
        return Response({"success": True, "data": {"matri_id": user.matri_id, "staff_id": sp.id, "staff_name": sp.name}})


class AdminProfileBlockAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, matri_id):
        user = _get_user_by_matri(matri_id)
        if not user:
            return Response({"success": False, "error": {"code": 404, "message": "Profile not found"}}, status=404)
        if not _can_edit(request, user):
            return Response({"success": False, "error": {"code": 403, "message": "Access denied"}}, status=403)

        admin = request.user
        au_mobile = (getattr(admin, "mobile", "") or "").replace(" ", "")
        u_mobile = (user.mobile or "").replace(" ", "")
        if au_mobile and u_mobile and au_mobile[-10:] == u_mobile[-10:]:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Cannot block your own account"}},
                status=400,
            )

        if request.data.get("blocked") is not None:
            user.is_blocked = bool(request.data["blocked"])
        else:
            user.is_blocked = not getattr(user, "is_blocked", False)
        user.save(update_fields=["is_blocked", "updated_at"])
        actor_nm = (getattr(request.user, "name", "") or "").strip()
        create_audit_log(
            request,
            action=AuditLog.ACTION_UPDATE_PROFILE,
            resource=f"profile:{user.matri_id}",
            details=f"{actor_nm} set blocked={user.is_blocked} for {user.name}.",
            target_profile_name=(user.name or "").strip(),
            action_type=AuditLog.ACTION_TYPE_UPDATE_PROFILE,
        )
        return Response({"success": True, "data": {"matri_id": user.matri_id, "is_blocked": user.is_blocked}})


class AdminProfileMergeAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if getattr(request.user, "role", None) != AdminUser.ROLE_ADMIN:
            return Response({"success": False, "error": {"code": 403, "message": "Insufficient permissions"}}, status=403)
        primary_id = (request.data.get("primary_matri_id") or "").strip()
        dup_id = (request.data.get("duplicate_matri_id") or "").strip()
        if not primary_id or not dup_id:
            return Response(
                {"success": False, "error": {"code": 400, "message": "primary_matri_id and duplicate_matri_id required"}},
                status=400,
            )
        if primary_id.lower() == dup_id.lower():
            return Response(
                {"success": False, "error": {"code": 400, "message": "Cannot merge a profile with itself"}},
                status=400,
            )
        primary = _get_user_by_matri(primary_id)
        duplicate = _get_user_by_matri(dup_id)
        if not primary or not duplicate:
            return Response({"success": False, "error": {"code": 404, "message": "Profile not found"}}, status=404)
        merge_user_accounts(primary, duplicate)
        actor_nm = (getattr(request.user, "name", "") or "").strip()
        create_audit_log(
            request,
            action=AuditLog.ACTION_UPDATE_PROFILE,
            resource=f"profile:{primary.matri_id}",
            details=f"{actor_nm} merged duplicate {duplicate.matri_id} into {primary.name}.",
            target_profile_name=(primary.name or "").strip(),
            action_type=AuditLog.ACTION_TYPE_UPDATE_PROFILE,
        )
        return Response(
            {
                "success": True,
                "data": {
                    "primary_matri_id": primary.matri_id,
                    "duplicate_retired_matri_id": duplicate.matri_id,
                },
            }
        )
