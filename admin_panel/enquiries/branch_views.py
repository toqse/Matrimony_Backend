"""
Branch Manager enquiry APIs — /api/v1/branch/enquiries/
Scoped to admin branch; uses BranchScopedMixin.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.models import AdminUser
from admin_panel.pagination import StandardPagination
from admin_panel.staff_mgmt.models import StaffProfile

from .mixins import BranchScopedMixin
from .models import Enquiry, EnquiryNote
from .scoping import manager_branch_code
from .serializers import (
    EnquiryAssignSerializer,
    EnquiryCreateSerializer,
    EnquiryMoveSerializer,
    EnquiryNoteCreateSerializer,
    EnquirySerializer,
)


def _first_serializer_error(serializer) -> str:
    for err in serializer.errors.values():
        if isinstance(err, list) and err:
            return str(err[0])
        if isinstance(err, dict):
            for v in err.values():
                if isinstance(v, list) and v:
                    return str(v[0])
        return str(err)
    return "Invalid request."


def _get_enquiry_for_branch(pk: int, mb):
    """
    Returns (enquiry, error_kind) where error_kind is None | 'not_found' | 'forbidden'.
    """
    try:
        enquiry = (
            Enquiry.objects.select_related("assigned_to", "branch")
            .prefetch_related("enquiry_notes__created_by")
            .get(pk=pk)
        )
    except Enquiry.DoesNotExist:
        return None, "not_found"
    if not mb or enquiry.branch_id != mb.pk:
        return None, "forbidden"
    return enquiry, None


def _base_branch_queryset(mb):
    return Enquiry.objects.filter(branch=mb).select_related("assigned_to", "branch").prefetch_related(
        "enquiry_notes__created_by"
    )


class BranchEnquirySummaryView(BranchScopedMixin, APIView):
    """GET .../summary/ — KPIs, pipeline counts, lead sources."""

    def get(self, request):
        mb, err = self.get_branch_manager_scope()
        if err:
            return err
        if not mb:
            return Response(
                {
                    "success": True,
                    "data": {
                        "total_enquiries": 0,
                        "active_leads": 0,
                        "converted": 0,
                        "overdue_followups": 0,
                        "pipeline": {
                            "new": 0,
                            "contacted": 0,
                            "interested": 0,
                            "converted": 0,
                            "lost": 0,
                        },
                        "sources": [],
                    },
                }
            )

        qs = _base_branch_queryset(mb)
        total_enquiries = qs.count()
        active_leads = qs.filter(status__in=["new", "contacted", "interested"]).count()
        converted = qs.filter(status="converted").count()

        overdue_cutoff = timezone.now() - timedelta(days=7)
        overdue_followups = qs.filter(
            status__in=["new", "contacted", "interested"],
            updated_at__lt=overdue_cutoff,
        ).count()

        pipeline = {}
        for st in ["new", "contacted", "interested", "converted", "lost"]:
            pipeline[st] = qs.filter(status=st).count()

        source_counts = {c[0]: 0 for c in Enquiry.SOURCE_CHOICES}
        for row in qs.values("source").annotate(c=Count("id")):
            source_counts[row["source"]] = row["c"]
        sources = [{"source": k, "count": v} for k, v in source_counts.items()]

        return Response(
            {
                "success": True,
                "data": {
                    "total_enquiries": total_enquiries,
                    "active_leads": active_leads,
                    "converted": converted,
                    "overdue_followups": overdue_followups,
                    "pipeline": pipeline,
                    "sources": sources,
                },
            }
        )


class BranchEnquiryListCreateView(BranchScopedMixin, APIView):
    """GET .../ — list; POST .../ — create."""

    def get(self, request):
        mb, err = self.get_branch_manager_scope()
        if err:
            return err
        if not mb:
            return Response(
                {
                    "success": True,
                    "data": {"count": 0, "next": None, "previous": None, "results": []},
                }
            )

        qs = _base_branch_queryset(mb)

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
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": 400,
                            "message": f"Invalid status filter. Must be one of: {', '.join(valid_statuses)}.",
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(status=status_filter)

        source = request.query_params.get("source")
        if source:
            valid_sources = ["website", "walk-in", "phone", "whatsapp", "email"]
            if source not in valid_sources:
                return Response(
                    {
                        "success": False,
                        "error": {"code": 400, "message": "Invalid source filter."},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(source=source)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs.order_by("-created_at"), request)
        serializer = EnquirySerializer(page, many=True)
        paginated = paginator.get_paginated_response(serializer.data)
        return Response(
            {
                "success": True,
                "data": {
                    "count": paginated.data["count"],
                    "next": paginated.data.get("next"),
                    "previous": paginated.data.get("previous"),
                    "results": paginated.data["results"],
                },
            }
        )

    def post(self, request):
        mb, err = self.get_branch_manager_scope()
        if err:
            return err
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

        user = request.user
        serializer = EnquiryCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": _first_serializer_error(serializer)},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = dict(serializer.validated_data)
        branch = data.get("branch")
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
        data["branch"] = mb

        enquiry = Enquiry.objects.create(created_by=user, **data)
        enquiry = (
            Enquiry.objects.select_related("assigned_to", "branch")
            .prefetch_related("enquiry_notes__created_by")
            .get(pk=enquiry.pk)
        )
        return Response(
            {"success": True, "data": EnquirySerializer(enquiry).data},
            status=status.HTTP_201_CREATED,
        )


class BranchEnquiryDetailView(BranchScopedMixin, APIView):
    """GET .../<id>/ — detail."""

    def get(self, request, pk):
        mb, err = self.get_branch_manager_scope()
        if err:
            return err
        enquiry, kind = _get_enquiry_for_branch(pk, mb)
        if kind == "not_found":
            return Response(
                {"success": False, "error": {"code": 404, "message": "Enquiry not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if kind == "forbidden":
            return Response(
                {"success": False, "error": {"code": 403, "message": "Access denied"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response({"success": True, "data": EnquirySerializer(enquiry).data})


class BranchEnquiryReassignView(BranchScopedMixin, APIView):
    """PATCH .../<id>/reassign/ — assign to branch staff."""

    def patch(self, request, pk):
        mb, err = self.get_branch_manager_scope()
        if err:
            return err
        enquiry, kind = _get_enquiry_for_branch(pk, mb)
        if kind == "not_found":
            return Response(
                {"success": False, "error": {"code": 404, "message": "Enquiry not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if kind == "forbidden":
            return Response(
                {"success": False, "error": {"code": 403, "message": "Access denied"}},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = EnquiryAssignSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": _first_serializer_error(serializer)},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        try:
            staff = AdminUser.objects.get(id=serializer.validated_data["staff_id"])
        except AdminUser.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Staff not found or inactive."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not staff.is_active:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Staff not found or inactive."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        sp = (
            StaffProfile.objects.select_related("branch")
            .filter(admin_user=staff, is_deleted=False)
            .first()
        )
        mgr_code = manager_branch_code(user)
        if not sp or not mgr_code:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Staff not found or inactive."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if sp.branch.code != mgr_code:
            return Response(
                {
                    "success": False,
                    "error": {"code": 403, "message": "Staff belongs to a different branch."},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        enquiry.assigned_to = staff
        enquiry.save(update_fields=["assigned_to", "updated_at"])
        return Response(
            {
                "success": True,
                "message": f"Enquiry assigned to {staff.name}.",
                "data": {"id": enquiry.id, "assigned_to": staff.name},
            }
        )


class BranchEnquiryMoveView(BranchScopedMixin, APIView):
    """PATCH .../<id>/move/ — pipeline status."""

    def patch(self, request, pk):
        mb, err = self.get_branch_manager_scope()
        if err:
            return err
        enquiry, kind = _get_enquiry_for_branch(pk, mb)
        if kind == "not_found":
            return Response(
                {"success": False, "error": {"code": 404, "message": "Enquiry not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if kind == "forbidden":
            return Response(
                {"success": False, "error": {"code": 403, "message": "Access denied"}},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = EnquiryMoveSerializer(data=request.data, context={"enquiry": enquiry})
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": _first_serializer_error(serializer)},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_status = serializer.validated_data["status"]
        old_status = enquiry.status
        enquiry.status = new_status
        enquiry.save(update_fields=["status", "updated_at"])

        return Response(
            {
                "success": True,
                "message": f"Enquiry moved from '{old_status}' to '{new_status}'.",
                "data": {"id": enquiry.id, "status": enquiry.status},
            }
        )


class BranchEnquiryAddNoteView(BranchScopedMixin, APIView):
    """POST .../<id>/notes/ — add note."""

    def post(self, request, pk):
        mb, err = self.get_branch_manager_scope()
        if err:
            return err
        enquiry, kind = _get_enquiry_for_branch(pk, mb)
        if kind == "not_found":
            return Response(
                {"success": False, "error": {"code": 404, "message": "Enquiry not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if kind == "forbidden":
            return Response(
                {"success": False, "error": {"code": 403, "message": "Access denied"}},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = EnquiryNoteCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": _first_serializer_error(serializer)},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        note = EnquiryNote.objects.create(
            enquiry=enquiry,
            text=serializer.validated_data["text"],
            created_by=request.user,
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
