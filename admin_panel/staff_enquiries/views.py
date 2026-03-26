from __future__ import annotations

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser
from admin_panel.enquiries.models import Enquiry, EnquiryNote
from admin_panel.enquiries.scoping import staff_enquiries_queryset, staff_profile_for
from admin_panel.enquiries.serializers import EnquiryMoveSerializer, EnquirySerializer
from admin_panel.pagination import StandardPagination
from admin_panel.staff_dashboard.services import resolve_staff_dashboard_request
from admin_panel.audit_log.utils import create_audit_log

from .serializers import StaffEnquiryCreateSerializer, StaffEnquiryNoteCreateSerializer

STAFF_ENQUIRY_404 = "Enquiry not found or not assigned to you."
REASSIGN_FORBIDDEN = "Reassigning enquiries requires Branch Manager or Admin role."


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


class _StaffEnquiryMixin:
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        u = getattr(request, "user", None)
        if u is not None and getattr(u, "is_authenticated", False):
            request.admin_user = u


def _get_staff_enquiry(pk: int, user: AdminUser):
    try:
        enquiry = (
            Enquiry.objects.select_related("assigned_to", "branch")
            .prefetch_related("enquiry_notes__created_by")
            .get(pk=pk)
        )
    except Enquiry.DoesNotExist:
        return None
    if enquiry.assigned_to_id != user.pk:
        return None
    return enquiry


def _reassign_in_payload(request) -> bool:
    if "assigned_to" not in request.data:
        return False
    raw = request.data.get("assigned_to")
    if raw in (None, ""):
        return False
    user = request.user
    try:
        aid = int(raw)
    except (TypeError, ValueError):
        return True
    return aid != user.pk


class StaffEnquirySummaryView(_StaffEnquiryMixin, APIView):
    """GET /api/v1/staff/enquiries/summary/"""

    def get(self, request):
        _, err = resolve_staff_dashboard_request(request)
        if err:
            return err
        user = request.user
        qs = staff_enquiries_queryset(user)
        total = qs.count()
        pipeline = {}
        for st in ["new", "contacted", "interested", "converted", "lost"]:
            pipeline[st] = qs.filter(status=st).count()
        return Response(
            {"success": True, "data": {"total": total, "pipeline": pipeline}}
        )


class StaffEnquiryListCreateView(_StaffEnquiryMixin, APIView):
    """GET/POST /api/v1/staff/enquiries/"""

    def get(self, request):
        _, err = resolve_staff_dashboard_request(request)
        if err:
            return err
        user = request.user
        qs = staff_enquiries_queryset(user)

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
            valid_sources = [
                "website",
                "walk-in",
                "phone",
                "whatsapp",
                "email",
            ]
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
        _, err = resolve_staff_dashboard_request(request)
        if err:
            return err
        if _reassign_in_payload(request):
            return Response(
                {
                    "success": False,
                    "error": {"code": 403, "message": REASSIGN_FORBIDDEN},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        user = request.user
        serializer = StaffEnquiryCreateSerializer(data=request.data)
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
        sp = staff_profile_for(user)
        if sp:
            if branch and branch.pk != sp.branch_id:
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
                branch = sp.branch

        email = data.get("email")
        if email == "":
            email = None

        enquiry = Enquiry.objects.create(
            created_by=user,
            name=data["name"],
            phone=data["phone"],
            email=email,
            source=data["source"],
            branch=branch,
            assigned_to=user,
        )
        enquiry = (
            Enquiry.objects.select_related("assigned_to", "branch")
            .prefetch_related("enquiry_notes__created_by")
            .get(pk=enquiry.pk)
        )
        create_audit_log(
            request,
            action="create",
            resource=f"enquiry:{enquiry.id}",
            details=f"Staff enquiry created for {enquiry.name}.",
        )
        return Response(
            {"success": True, "data": EnquirySerializer(enquiry).data},
            status=status.HTTP_201_CREATED,
        )


class StaffEnquiryDetailView(_StaffEnquiryMixin, APIView):
    """GET /api/v1/staff/enquiries/<id>/"""

    def get(self, request, pk):
        _, err = resolve_staff_dashboard_request(request)
        if err:
            return err
        enquiry = _get_staff_enquiry(pk, request.user)
        if not enquiry:
            return Response(
                {
                    "success": False,
                    "error": {"code": 404, "message": STAFF_ENQUIRY_404},
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"success": True, "data": EnquirySerializer(enquiry).data})


class StaffEnquiryMoveView(_StaffEnquiryMixin, APIView):
    """PATCH /api/v1/staff/enquiries/<id>/move/"""

    def patch(self, request, pk):
        _, err = resolve_staff_dashboard_request(request)
        if err:
            return err
        if "assigned_to" in request.data:
            return Response(
                {
                    "success": False,
                    "error": {"code": 403, "message": REASSIGN_FORBIDDEN},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        enquiry = _get_staff_enquiry(pk, request.user)
        if not enquiry:
            return Response(
                {
                    "success": False,
                    "error": {"code": 404, "message": STAFF_ENQUIRY_404},
                },
                status=status.HTTP_404_NOT_FOUND,
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


class StaffEnquiryAddNoteView(_StaffEnquiryMixin, APIView):
    """POST /api/v1/staff/enquiries/<id>/notes/"""

    def post(self, request, pk):
        _, err = resolve_staff_dashboard_request(request)
        if err:
            return err
        enquiry = _get_staff_enquiry(pk, request.user)
        if not enquiry:
            return Response(
                {
                    "success": False,
                    "error": {"code": 404, "message": STAFF_ENQUIRY_404},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = StaffEnquiryNoteCreateSerializer(data=request.data)
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
            created_by=request.user,
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
