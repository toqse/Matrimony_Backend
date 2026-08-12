from __future__ import annotations

from django.db.models import Count, Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.pagination import StandardPagination
from admin_panel.permissions import IsAdminOrBranchManager, IsStaffOrAbove
from admin_panel.branches.models import Branch
from admin_panel.staff_mgmt.models import StaffProfile
from admin_panel.audit_log.utils import create_audit_log

from .models import Enquiry, EnquiryNote
from .scoping import admin_branch_for_manager, manager_branch_code, staff_profile_for
from .serializers import (
    EnquiryAssignSerializer,
    EnquiryCreateSerializer,
    EnquiryMoveSerializer,
    EnquiryNoteCreateSerializer,
    EnquirySerializer,
)


class _AdminUserMixin:
    """Match spec: `request.admin_user` is the authenticated AdminUser."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        u = getattr(request, "user", None)
        if u is not None and getattr(u, "is_authenticated", False):
            request.admin_user = u


def _first_serializer_error(serializer) -> str:
    for err in serializer.errors.values():
        if isinstance(err, list) and err:
            return str(err[0])
        return str(err)
    return "Invalid request."


def _enquiry_scope_ok(user: AdminUser, enquiry: Enquiry) -> bool:
    if user.role == AdminUser.ROLE_ADMIN:
        return True
    if user.role == AdminUser.ROLE_BRANCH_MANAGER:
        mb = admin_branch_for_manager(user)
        return bool(mb and enquiry.branch_id == mb.pk)
    if user.role == AdminUser.ROLE_STAFF:
        return enquiry.assigned_to_id == user.pk
    return False


def _parse_branch_id_param(raw) -> int | None:
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _branch_options(qs) -> list[dict]:
    return [{"id": b.pk, "name": b.name} for b in qs.order_by("name")]


def _staff_options(qs) -> list[dict]:
    return [
        {
            "id": sp.admin_user_id,
            "name": sp.name,
            "branch_id": sp.branch_id,
            "branch_name": sp.branch.name if sp.branch_id else "",
        }
        for sp in qs.select_related("branch", "admin_user").order_by("name")
        if sp.admin_user_id
    ]


def _assignable_staff_queryset(*, branch_id: int | None = None):
    qs = StaffProfile.objects.filter(
        is_deleted=False,
        is_active=True,
        admin_user__isnull=False,
        admin_user__is_active=True,
        admin_user__role=AdminUser.ROLE_STAFF,
    )
    if branch_id is not None:
        qs = qs.filter(branch_id=branch_id)
    return qs


class EnquiryFormOptionsView(_AdminUserMixin, APIView):
    """
    GET /api/v1/admin/enquiries/options/ — Branch + staff lists for Add Enquiry form.

    staff[].id is AdminUser pk (Enquiry.assigned_to), not StaffProfile pk.
    Optional ?branch_id= filters staff to one branch (cascading dropdown).
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsStaffOrAbove]

    def get(self, request):
        user = request.user
        filter_branch_id = _parse_branch_id_param(request.query_params.get("branch_id"))

        if user.role == AdminUser.ROLE_ADMIN:
            branches_qs = Branch.objects.filter(is_deleted=False, is_active=True)
            staff_qs = _assignable_staff_queryset(branch_id=filter_branch_id)

        elif user.role == AdminUser.ROLE_BRANCH_MANAGER:
            mb = admin_branch_for_manager(user)
            if not mb:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": 400,
                            "message": "No branch assigned to your account. Contact admin.",
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            branches_qs = Branch.objects.filter(pk=mb.pk, is_deleted=False, is_active=True)
            mgr_code = manager_branch_code(user)
            staff_qs = _assignable_staff_queryset().filter(branch__code=mgr_code)
            if filter_branch_id is not None:
                if filter_branch_id != mb.pk:
                    staff_qs = staff_qs.none()
                else:
                    staff_qs = staff_qs.filter(branch_id=filter_branch_id)

        elif user.role == AdminUser.ROLE_STAFF:
            sp = staff_profile_for(user)
            if not sp or not sp.branch_id:
                return Response(
                    {"success": True, "data": {"branches": [], "staff": []}},
                    status=status.HTTP_200_OK,
                )
            branches_qs = Branch.objects.filter(
                pk=sp.branch_id, is_deleted=False, is_active=True
            )
            staff_qs = StaffProfile.objects.filter(
                pk=sp.pk,
                is_deleted=False,
                is_active=True,
                admin_user__isnull=False,
            )
            if filter_branch_id is not None and filter_branch_id != sp.branch_id:
                staff_qs = staff_qs.none()

        else:
            return Response(
                {
                    "success": False,
                    "error": {"code": 403, "message": "Insufficient permissions."},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {
                "success": True,
                "data": {
                    "branches": _branch_options(branches_qs),
                    "staff": _staff_options(staff_qs),
                },
            },
            status=status.HTTP_200_OK,
        )


class EnquiryListCreateView(_AdminUserMixin, APIView):
    """
    GET  /api/v1/admin/enquiries/   — Paginated list with filters
    POST /api/v1/admin/enquiries/   — Create new enquiry
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsStaffOrAbove]

    def get_queryset(self, request):
        user = request.user
        qs = Enquiry.objects.select_related("assigned_to", "branch").prefetch_related(
            "enquiry_notes__created_by"
        )

        if user.role == AdminUser.ROLE_BRANCH_MANAGER:
            mb = admin_branch_for_manager(user)
            qs = qs.filter(branch=mb) if mb else qs.none()
        elif user.role == AdminUser.ROLE_STAFF:
            qs = qs.filter(assigned_to=user)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )

        status_filter = request.query_params.get("status")
        if status_filter:
            valid_statuses = ["new", "contacted", "interested", "converted", "lost"]
            if status_filter not in valid_statuses:
                raise ValueError(
                    f"Invalid status filter. Must be one of: {', '.join(valid_statuses)}."
                )
            qs = qs.filter(status=status_filter)

        source = request.query_params.get("source")
        if source:
            valid_sources = ["website", "walk-in", "phone", "whatsapp", "email"]
            if source not in valid_sources:
                raise ValueError("Invalid source filter.")
            qs = qs.filter(source=source)

        branch_id = request.query_params.get("branch_id")
        if branch_id and user.role == AdminUser.ROLE_ADMIN:
            qs = qs.filter(branch_id=branch_id)

        staff_id = request.query_params.get("staff_id")
        if staff_id and user.role in (
            AdminUser.ROLE_ADMIN,
            AdminUser.ROLE_BRANCH_MANAGER,
        ):
            qs = qs.filter(assigned_to_id=staff_id)

        return qs

    def get(self, request):
        try:
            qs = self.get_queryset(request)
        except ValueError as e:
            return Response(
                {"success": False, "error": {"code": 400, "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = EnquirySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        user = request.user
        serializer = EnquiryCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": 400,
                        "message": _first_serializer_error(serializer),
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = dict(serializer.validated_data)
        branch = data.get("branch")

        if user.role == AdminUser.ROLE_BRANCH_MANAGER:
            mb = admin_branch_for_manager(user)
            if not mb:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": 403,
                            "message": "Access denied. Cannot create enquiry in another branch.",
                        },
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            if branch and branch.pk != mb.pk:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": 403,
                            "message": "Access denied. Cannot create enquiry in another branch.",
                        },
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            if not branch:
                data["branch"] = mb

        if user.role == AdminUser.ROLE_STAFF:
            sp = staff_profile_for(user)
            if sp and not branch:
                data["branch"] = sp.branch
            if not data.get("assigned_to"):
                data["assigned_to"] = user

        enquiry = Enquiry.objects.create(created_by=user, **data)
        enquiry = (
            Enquiry.objects.select_related("assigned_to", "branch")
            .prefetch_related("enquiry_notes__created_by")
            .get(pk=enquiry.pk)
        )
        create_audit_log(
            request,
            action="create",
            resource=f"enquiry:{enquiry.id}",
            details=f"Enquiry created for {enquiry.name}.",
        )
        return Response(
            {"success": True, "data": EnquirySerializer(enquiry).data},
            status=status.HTTP_201_CREATED,
        )


class EnquiryDetailView(_AdminUserMixin, APIView):
    """
    GET /api/v1/admin/enquiries/{id}/ — Enquiry detail with notes
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsStaffOrAbove]

    def get_object(self, pk, request):
        user = request.user
        try:
            enquiry = (
                Enquiry.objects.select_related("assigned_to", "branch")
                .prefetch_related("enquiry_notes__created_by")
                .get(pk=pk)
            )
        except Enquiry.DoesNotExist:
            return None

        if not _enquiry_scope_ok(user, enquiry):
            return None
        return enquiry

    def get(self, request, pk):
        enquiry = self.get_object(pk, request)
        if not enquiry:
            return Response(
                {
                    "success": False,
                    "error": {"code": 404, "message": "Enquiry not found."},
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"success": True, "data": EnquirySerializer(enquiry).data})


class EnquiryMoveView(_AdminUserMixin, APIView):
    """
    PATCH /api/v1/admin/enquiries/{id}/move/ — Move to new status
    Body: { "status": "interested" }
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsStaffOrAbove]

    def patch(self, request, pk):
        try:
            enquiry = Enquiry.objects.get(pk=pk)
        except Enquiry.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "error": {"code": 404, "message": "Enquiry not found."},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        user = request.user
        if not _enquiry_scope_ok(user, enquiry):
            return Response(
                {
                    "success": False,
                    "error": {"code": 404, "message": "Enquiry not found."},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.role == AdminUser.ROLE_STAFF and enquiry.assigned_to_id != user.pk:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": 403,
                        "message": "You can only update enquiries assigned to you.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = EnquiryMoveSerializer(
            data=request.data, context={"enquiry": enquiry}
        )
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": 400,
                        "message": _first_serializer_error(serializer),
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_status = serializer.validated_data["status"]
        old_status = enquiry.status
        enquiry.status = new_status
        enquiry.save(update_fields=["status", "updated_at"])
        create_audit_log(
            request,
            action="update",
            resource=f"enquiry:{enquiry.id}",
            details=f"Enquiry status moved from {old_status} to {new_status}.",
        )

        return Response(
            {
                "success": True,
                "message": f"Enquiry moved from '{old_status}' to '{new_status}'.",
                "data": {"id": enquiry.id, "status": enquiry.status},
            }
        )


class EnquiryAssignView(_AdminUserMixin, APIView):
    """
    PATCH /api/v1/admin/enquiries/{id}/assign/ — Assign to staff
    Body: { "staff_id": 2 }
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminOrBranchManager]

    def patch(self, request, pk):
        try:
            enquiry = Enquiry.objects.get(pk=pk)
        except Enquiry.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "error": {"code": 404, "message": "Enquiry not found."},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        user = request.user
        if user.role == AdminUser.ROLE_BRANCH_MANAGER:
            mb = admin_branch_for_manager(user)
            if not mb or enquiry.branch_id != mb.pk:
                return Response(
                    {
                        "success": False,
                        "error": {"code": 404, "message": "Enquiry not found."},
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        serializer = EnquiryAssignSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": 400,
                        "message": _first_serializer_error(serializer),
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        staff = AdminUser.objects.get(id=serializer.validated_data["staff_id"])
        sp = (
            StaffProfile.objects.select_related("branch")
            .filter(admin_user=staff, is_deleted=False)
            .first()
        )

        if user.role == AdminUser.ROLE_BRANCH_MANAGER:
            mgr_code = manager_branch_code(user)
            if (
                not sp
                or not mgr_code
                or sp.branch.code != mgr_code
            ):
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": 403,
                            "message": "Staff belongs to a different branch.",
                        },
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        enquiry.assigned_to = staff
        enquiry.save(update_fields=["assigned_to", "updated_at"])
        create_audit_log(
            request,
            action="update",
            resource=f"enquiry:{enquiry.id}",
            details=f"Enquiry assigned to {staff.name}.",
        )
        return Response(
            {
                "success": True,
                "message": f"Enquiry assigned to {staff.name}.",
                "data": {"id": enquiry.id, "assigned_to": staff.name},
            }
        )


class EnquiryAddNoteView(_AdminUserMixin, APIView):
    """
    POST /api/v1/admin/enquiries/{id}/notes/ — Add a note
    Body: { "text": "Called the customer..." }
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsStaffOrAbove]

    def post(self, request, pk):
        try:
            enquiry = Enquiry.objects.get(pk=pk)
        except Enquiry.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "error": {"code": 404, "message": "Enquiry not found."},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        user = request.user
        if not _enquiry_scope_ok(user, enquiry):
            return Response(
                {
                    "success": False,
                    "error": {"code": 404, "message": "Enquiry not found."},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.role == AdminUser.ROLE_STAFF and enquiry.assigned_to_id != user.pk:
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": 403,
                        "message": "You can only add notes to your assigned enquiries.",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = EnquiryNoteCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": 400,
                        "message": _first_serializer_error(serializer),
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        note = EnquiryNote.objects.create(
            enquiry=enquiry,
            text=serializer.validated_data["text"],
            created_by=user,
        )
        create_audit_log(
            request,
            action="update",
            resource=f"enquiry:{enquiry.id}",
            details="Enquiry note added.",
        )
        return Response(
            {
                "success": True,
                "message": "Note added successfully.",
                "data": {
                    "id": note.id,
                    "text": note.text,
                    "created_at": note.created_at,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class EnquiryKanbanView(_AdminUserMixin, APIView):
    """
    GET /api/v1/admin/enquiries/kanban/ — Grouped by status.
    Full column counts; items capped per column for payload size.
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsStaffOrAbove]
    KANBAN_ITEMS_PER_COLUMN = 50

    def get(self, request):
        user = request.user
        qs = Enquiry.objects.select_related("assigned_to", "branch")

        if user.role == AdminUser.ROLE_BRANCH_MANAGER:
            mb = admin_branch_for_manager(user)
            qs = qs.filter(branch=mb) if mb else qs.none()
        elif user.role == AdminUser.ROLE_STAFF:
            qs = qs.filter(assigned_to=user)

        columns = ["new", "contacted", "interested", "converted", "lost"]
        counts = {
            row["status"]: row["c"]
            for row in qs.values("status").annotate(c=Count("id"))
        }

        result = {}
        per_col = self.KANBAN_ITEMS_PER_COLUMN
        for col in columns:
            col_qs = (
                qs.filter(status=col)
                .prefetch_related("enquiry_notes__created_by")
                .order_by("-updated_at", "-pk")[:per_col]
            )
            result[col] = {
                "count": int(counts.get(col, 0)),
                "items": EnquirySerializer(col_qs, many=True).data,
            }

        return Response({"success": True, "data": result})
