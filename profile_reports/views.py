"""
Member and admin APIs for profile reports.
"""
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.permissions import IsAdminUser

from .models import ProfileReport
from .serializers import ProfileReportCreateSerializer, ProfileReportStatusSerializer


def _parse_page_params(request, default_page_size=20, max_page_size=50):
    try:
        page = max(1, int(request.query_params.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    raw_page_size = request.query_params.get('page_size')
    if raw_page_size is None:
        raw_page_size = request.query_params.get('limit', default_page_size)
    try:
        page_size = int(raw_page_size)
    except (TypeError, ValueError):
        page_size = default_page_size
    page_size = max(1, min(max_page_size, page_size))
    return page, page_size


def _serialize_admin_row(report: ProfileReport) -> dict:
    reporter = report.reporter
    reported = report.reported
    return {
        'id': report.id,
        'reporter_matri_id': reporter.matri_id or '',
        'reporter_name': reporter.name or '',
        'reported_matri_id': reported.matri_id or '',
        'reported_name': reported.name or '',
        'message': report.message,
        'status': report.status,
        'created_at': report.created_at.isoformat() if report.created_at else None,
        'updated_at': report.updated_at.isoformat() if report.updated_at else None,
    }


class MemberProfileReportCreateView(APIView):
    """POST /api/v1/profile-reports/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = ProfileReportCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        matri_id = (ser.validated_data['matri_id'] or '').strip()
        message = (ser.validated_data['message'] or '').strip()
        if not message:
            return Response({
                'success': False,
                'error': {'code': 400, 'message': 'Message is required.'},
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            target = User.objects.get(matri_id=matri_id, is_active=True)
        except User.DoesNotExist:
            return Response({
                'success': False,
                'error': {'code': 404, 'message': 'Profile not found.'},
            }, status=status.HTTP_404_NOT_FOUND)

        if target.pk == request.user.pk:
            return Response({
                'success': False,
                'error': {'code': 403, 'message': 'Cannot report your own profile.'},
            }, status=status.HTTP_403_FORBIDDEN)

        report = ProfileReport.objects.create(
            reporter=request.user,
            reported=target,
            message=message,
            status=ProfileReport.STATUS_PENDING,
        )
        return Response({
            'success': True,
            'message': 'Report submitted.',
            'data': {
                'id': report.id,
                'matri_id': target.matri_id,
                'status': report.status,
            },
        }, status=status.HTTP_200_OK)


class AdminProfileReportListView(APIView):
    """GET /api/v1/admin/profile-reports/"""
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        page, page_size = _parse_page_params(request)
        status_filter = (request.query_params.get('status') or '').strip().lower()
        qs = ProfileReport.objects.select_related('reporter', 'reported').order_by('-created_at')
        if status_filter in (
            ProfileReport.STATUS_PENDING,
            ProfileReport.STATUS_REVIEWED,
            ProfileReport.STATUS_DISMISSED,
        ):
            qs = qs.filter(status=status_filter)

        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(reporter__matri_id__icontains=search)
                | Q(reported__matri_id__icontains=search)
                | Q(reporter__name__icontains=search)
                | Q(reported__name__icontains=search)
                | Q(message__icontains=search)
            )

        total = qs.count()
        start = (page - 1) * page_size
        page_qs = qs[start:start + page_size]
        results = [_serialize_admin_row(r) for r in page_qs]
        return Response({
            'success': True,
            'data': {
                'total': total,
                'page': page,
                'page_size': page_size,
                'results': results,
            },
        }, status=status.HTTP_200_OK)


class AdminProfileReportStatusView(APIView):
    """PATCH /api/v1/admin/profile-reports/{id}/"""
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminUser]

    def patch(self, request, report_id):
        ser = ProfileReportStatusSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            report = ProfileReport.objects.select_related('reporter', 'reported').get(pk=report_id)
        except ProfileReport.DoesNotExist:
            return Response({
                'success': False,
                'error': {'code': 404, 'message': 'Report not found.'},
            }, status=status.HTTP_404_NOT_FOUND)

        report.status = ser.validated_data['status']
        report.save(update_fields=['status', 'updated_at'])
        return Response({
            'success': True,
            'message': 'Report status updated.',
            'data': _serialize_admin_row(report),
        }, status=status.HTTP_200_OK)
