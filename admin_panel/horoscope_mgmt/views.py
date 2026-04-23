from __future__ import annotations

from uuid import UUID

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.permissions import IsAdminUser, IsBranchManagerOnly

from .permissions import IsPanelStaff
from .serializers import PanelPoruthamRequestSerializer
from . import services as horoscope_panel


def _resolve_qs(request, mount: str):
    qs = horoscope_panel.scoped_member_users_queryset(request, mount=mount)
    if qs is None:
        return None, Response(
            {"success": False, "error": {"code": 403, "message": "Access denied or invalid panel context."}},
            status=status.HTTP_403_FORBIDDEN,
        )
    return qs, None


class HoroscopePanelSummaryView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    mount = "admin"

    def get_permissions(self):
        if self.mount == "admin":
            return [IsAuthenticated(), IsAdminUser()]
        if self.mount == "staff":
            return [IsAuthenticated(), IsPanelStaff()]
        return [IsAuthenticated(), IsBranchManagerOnly()]

    def get(self, request):
        qs, err = _resolve_qs(request, self.mount)
        if err:
            return err
        data = horoscope_panel.build_summary_counts(qs)
        return Response({"success": True, "data": data}, status=status.HTTP_200_OK)


class HoroscopePanelRecordsView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    mount = "admin"  # overridden by clones

    def get_permissions(self):
        if self.mount == "admin":
            return [IsAuthenticated(), IsAdminUser()]
        if self.mount == "staff":
            return [IsAuthenticated(), IsPanelStaff()]
        return [IsAuthenticated(), IsBranchManagerOnly()]

    def get(self, request):
        qs, err = _resolve_qs(request, self.mount)
        if err:
            return err
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = max(1, min(100, int(request.query_params.get("page_size", 20))))
        except (TypeError, ValueError):
            page_size = 20
        search = (request.query_params.get("search") or "").strip()
        branch_id = request.query_params.get("branch_id")
        data = horoscope_panel.list_horoscope_records(
            qs, search=search, branch_id=branch_id, page=page, page_size=page_size
        )
        return Response({"success": True, "data": data}, status=status.HTTP_200_OK)


class HoroscopePanelRecordDetailView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    mount = "admin"

    def get_permissions(self):
        if self.mount == "admin":
            return [IsAuthenticated(), IsAdminUser()]
        if self.mount == "staff":
            return [IsAuthenticated(), IsPanelStaff()]
        return [IsAuthenticated(), IsBranchManagerOnly()]

    def get(self, request, user_id):
        qs, err = _resolve_qs(request, self.mount)
        if err:
            return err
        try:
            uid = UUID(str(user_id))
        except (ValueError, TypeError):
            return Response(
                {"success": False, "error": {"code": 400, "message": "Invalid user id."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = horoscope_panel.record_detail(qs, uid)
        if not data:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Profile not found or out of scope."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"success": True, "data": data}, status=status.HTTP_200_OK)


class HoroscopePanelRecordByMatriView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    mount = "admin"

    def get_permissions(self):
        if self.mount == "admin":
            return [IsAuthenticated(), IsAdminUser()]
        if self.mount == "staff":
            return [IsAuthenticated(), IsPanelStaff()]
        return [IsAuthenticated(), IsBranchManagerOnly()]

    def get(self, request, matri_id):
        qs, err = _resolve_qs(request, self.mount)
        if err:
            return err
        data = horoscope_panel.record_detail_by_matri(qs, matri_id)
        if not data:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Profile not found or out of scope."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"success": True, "data": data}, status=status.HTTP_200_OK)


class HoroscopePanelRegenerateView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    mount = "admin"

    def get_permissions(self):
        if self.mount == "admin":
            return [IsAuthenticated(), IsAdminUser()]
        if self.mount == "staff":
            return [IsAuthenticated(), IsPanelStaff()]
        return [IsAuthenticated(), IsBranchManagerOnly()]

    def post(self, request, user_id):
        qs, err = _resolve_qs(request, self.mount)
        if err:
            return err
        try:
            uid = UUID(str(user_id))
        except (ValueError, TypeError):
            return Response(
                {"success": False, "error": {"code": 400, "message": "Invalid user id."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data, msg = horoscope_panel.regenerate_horoscope(qs, uid)
        if msg:
            return Response(
                {"success": False, "error": {"code": 400, "message": msg}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"success": True, "data": data}, status=status.HTTP_200_OK)


class HoroscopePanelPoruthamView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    mount = "admin"

    def get_permissions(self):
        if self.mount == "admin":
            return [IsAuthenticated(), IsAdminUser()]
        if self.mount == "staff":
            return [IsAuthenticated(), IsPanelStaff()]
        return [IsAuthenticated(), IsBranchManagerOnly()]

    def post(self, request):
        qs, err = _resolve_qs(request, self.mount)
        if err:
            return err
        ser = PanelPoruthamRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        chart_style = (request.query_params.get("chart_style") or "south").strip() or "south"
        result, msg = horoscope_panel.panel_porutham(
            qs,
            ser.validated_data["bride_profile_id"],
            ser.validated_data["groom_profile_id"],
            request=request,
            chart_style=chart_style,
        )
        if msg:
            return Response(
                {"success": False, "error": {"code": 400, "message": msg}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"success": True, "data": result}, status=status.HTTP_200_OK)


class HoroscopePanelJathakamPdfsView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    mount = "admin"

    def get_permissions(self):
        if self.mount == "admin":
            return [IsAuthenticated(), IsAdminUser()]
        if self.mount == "staff":
            return [IsAuthenticated(), IsPanelStaff()]
        return [IsAuthenticated(), IsBranchManagerOnly()]

    def get(self, request):
        qs, err = _resolve_qs(request, self.mount)
        if err:
            return err
        data = horoscope_panel.list_jathakam_pdf_credits(qs)
        return Response({"success": True, "data": {"results": data}}, status=status.HTTP_200_OK)


def _clone_view_attrs(source, mount: str):
    """Copy DRF view class with a different ``mount`` (admin | staff | branch)."""
    return type(f"{source.__name__}_{mount}", (source,), {"mount": mount})


AdminHoroscopePanelSummaryView = _clone_view_attrs(HoroscopePanelSummaryView, "admin")
StaffHoroscopePanelSummaryView = _clone_view_attrs(HoroscopePanelSummaryView, "staff")
BranchHoroscopePanelSummaryView = _clone_view_attrs(HoroscopePanelSummaryView, "branch")

AdminHoroscopePanelRecordsView = _clone_view_attrs(HoroscopePanelRecordsView, "admin")
StaffHoroscopePanelRecordsView = _clone_view_attrs(HoroscopePanelRecordsView, "staff")
BranchHoroscopePanelRecordsView = _clone_view_attrs(HoroscopePanelRecordsView, "branch")

AdminHoroscopePanelRecordDetailView = _clone_view_attrs(HoroscopePanelRecordDetailView, "admin")
StaffHoroscopePanelRecordDetailView = _clone_view_attrs(HoroscopePanelRecordDetailView, "staff")
BranchHoroscopePanelRecordDetailView = _clone_view_attrs(HoroscopePanelRecordDetailView, "branch")

AdminHoroscopePanelRecordByMatriView = _clone_view_attrs(HoroscopePanelRecordByMatriView, "admin")
StaffHoroscopePanelRecordByMatriView = _clone_view_attrs(HoroscopePanelRecordByMatriView, "staff")
BranchHoroscopePanelRecordByMatriView = _clone_view_attrs(HoroscopePanelRecordByMatriView, "branch")

AdminHoroscopePanelRegenerateView = _clone_view_attrs(HoroscopePanelRegenerateView, "admin")
StaffHoroscopePanelRegenerateView = _clone_view_attrs(HoroscopePanelRegenerateView, "staff")
BranchHoroscopePanelRegenerateView = _clone_view_attrs(HoroscopePanelRegenerateView, "branch")

AdminHoroscopePanelPoruthamView = _clone_view_attrs(HoroscopePanelPoruthamView, "admin")
StaffHoroscopePanelPoruthamView = _clone_view_attrs(HoroscopePanelPoruthamView, "staff")
BranchHoroscopePanelPoruthamView = _clone_view_attrs(HoroscopePanelPoruthamView, "branch")

AdminHoroscopePanelJathakamPdfsView = _clone_view_attrs(HoroscopePanelJathakamPdfsView, "admin")
StaffHoroscopePanelJathakamPdfsView = _clone_view_attrs(HoroscopePanelJathakamPdfsView, "staff")
BranchHoroscopePanelJathakamPdfsView = _clone_view_attrs(HoroscopePanelJathakamPdfsView, "branch")
