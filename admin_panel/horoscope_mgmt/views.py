from __future__ import annotations

from uuid import UUID

from django.http import HttpResponse
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
            qs,
            search=search,
            branch_id=branch_id,
            page=page,
            page_size=page_size,
            request=request,
            mount=self.mount,
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
        data = horoscope_panel.record_detail(
            qs, uid, request=request, mount=self.mount
        )
        if not data:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Profile not found or out of scope."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"success": True, "data": data}, status=status.HTTP_200_OK)


class HoroscopePanelJathagamPdfDownloadView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    mount = "admin"

    def get_permissions(self):
        if self.mount == "admin":
            return [IsAuthenticated(), IsAdminUser()]
        if self.mount == "staff":
            return [IsAuthenticated(), IsPanelStaff()]
        return [IsAuthenticated(), IsBranchManagerOnly()]

    def get(self, request, horoscope_id):
        from astrology.jathagam import generate_pdf

        qs, err = _resolve_qs(request, self.mount)
        if err:
            return err
        hp = horoscope_panel.get_horoscope_in_scope(qs, horoscope_id)
        if not hp:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Horoscope not found or out of scope."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not hp.pr_rasi or len(hp.pr_rasi) < 11:
            return Response(
                {
                    "success": False,
                    "error": {"code": 400, "message": "Horoscope not calculated yet."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        content, fmt = generate_pdf(hp)
        name = f"jathagam_{hp.pr_name}_{hp.pr_dob}".replace(' ', '_')
        if fmt == 'pdf':
            resp = HttpResponse(content, content_type='application/pdf')
            resp['Content-Disposition'] = f'attachment; filename="{name}.pdf"'
            return resp
        return HttpResponse(content, content_type='text/html')


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
        data = horoscope_panel.record_detail_by_matri(
            qs, matri_id, request=request, mount=self.mount
        )
        if not data:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Profile not found or out of scope."}},
                status=status.HTTP_404_NOT_FOUND,
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


class HoroscopePanelMatchReportView(APIView):
    """GET /api/v1/admin/horoscope/match-report/?bride_profile_id=&groom_profile_id="""

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

        try:
            bride_profile_id = int(request.query_params.get("bride_profile_id", ""))
            groom_profile_id = int(request.query_params.get("groom_profile_id", ""))
        except (TypeError, ValueError):
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": 400,
                        "message": "bride_profile_id and groom_profile_id are required integers.",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        content, fmt, msg = horoscope_panel.build_match_report(
            qs, bride_profile_id, groom_profile_id
        )
        if msg:
            code = 404 if "out of scope" in msg or "Invalid profile" in msg else 400
            return Response(
                {"success": False, "error": {"code": code, "message": msg}},
                status=status.HTTP_404_NOT_FOUND if code == 404 else status.HTTP_400_BAD_REQUEST,
            )

        from profiles.models import UserProfile

        b_prof = UserProfile.objects.select_related("user").filter(pk=bride_profile_id).first()
        g_prof = UserProfile.objects.select_related("user").filter(pk=groom_profile_id).first()
        b_id = (b_prof.user.matri_id if b_prof and b_prof.user else "") or str(bride_profile_id)
        g_id = (g_prof.user.matri_id if g_prof and g_prof.user else "") or str(groom_profile_id)
        name = f"match_report_{b_id}_{g_id}".replace(" ", "_")
        ct = "application/pdf" if fmt == "pdf" else "text/html"
        resp = HttpResponse(content, content_type=ct)
        resp["Content-Disposition"] = f'attachment; filename="{name}.pdf"'
        return resp


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


class HoroscopePanelSyncView(APIView):
    """POST: fill derived horoscope fields for pending in-scope profiles."""

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
        result = horoscope_panel.run_mark_horoscope_done(qs)
        return Response({"success": True, "data": result}, status=status.HTTP_200_OK)


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

AdminHoroscopePanelJathagamPdfDownloadView = _clone_view_attrs(
    HoroscopePanelJathagamPdfDownloadView, "admin"
)
StaffHoroscopePanelJathagamPdfDownloadView = _clone_view_attrs(
    HoroscopePanelJathagamPdfDownloadView, "staff"
)
BranchHoroscopePanelJathagamPdfDownloadView = _clone_view_attrs(
    HoroscopePanelJathagamPdfDownloadView, "branch"
)

AdminHoroscopePanelRecordByMatriView = _clone_view_attrs(HoroscopePanelRecordByMatriView, "admin")
StaffHoroscopePanelRecordByMatriView = _clone_view_attrs(HoroscopePanelRecordByMatriView, "staff")
BranchHoroscopePanelRecordByMatriView = _clone_view_attrs(HoroscopePanelRecordByMatriView, "branch")

AdminHoroscopePanelPoruthamView = _clone_view_attrs(HoroscopePanelPoruthamView, "admin")
StaffHoroscopePanelPoruthamView = _clone_view_attrs(HoroscopePanelPoruthamView, "staff")
BranchHoroscopePanelPoruthamView = _clone_view_attrs(HoroscopePanelPoruthamView, "branch")

AdminHoroscopePanelJathakamPdfsView = _clone_view_attrs(HoroscopePanelJathakamPdfsView, "admin")
StaffHoroscopePanelJathakamPdfsView = _clone_view_attrs(HoroscopePanelJathakamPdfsView, "staff")
BranchHoroscopePanelJathakamPdfsView = _clone_view_attrs(HoroscopePanelJathakamPdfsView, "branch")

AdminHoroscopePanelSyncView = _clone_view_attrs(HoroscopePanelSyncView, "admin")
StaffHoroscopePanelSyncView = _clone_view_attrs(HoroscopePanelSyncView, "staff")
BranchHoroscopePanelSyncView = _clone_view_attrs(HoroscopePanelSyncView, "branch")

AdminHoroscopePanelMatchReportView = _clone_view_attrs(HoroscopePanelMatchReportView, "admin")
StaffHoroscopePanelMatchReportView = _clone_view_attrs(HoroscopePanelMatchReportView, "staff")
BranchHoroscopePanelMatchReportView = _clone_view_attrs(HoroscopePanelMatchReportView, "branch")
