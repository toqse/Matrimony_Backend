"""
Member block APIs: POST/DELETE/GET /api/v1/blocks/
"""
from django.db import IntegrityError
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.models import User
from matches.utils import compute_match_percentage
from wishlist.models import Wishlist
from wishlist.serializers import _build_wishlist_profile_dict
from .models import UserBlock
from .serializers import BlockedProfileSerializer


def _safe_one_to_one(obj, rel_name):
    try:
        return getattr(obj, rel_name)
    except ObjectDoesNotExist:
        return None


def _parse_page_params(request, default_page_size=10, max_page_size=50):
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


def _resolve_target(matri_id):
    matri_id = (matri_id or '').strip()
    if not matri_id:
        return None, Response({
            'success': False,
            'error': {'code': 400, 'message': 'matri_id is required.'},
        }, status=status.HTTP_400_BAD_REQUEST)
    try:
        # Allow blocking even if target later becomes inactive; prefer active lookup first.
        target = User.objects.get(matri_id=matri_id, is_active=True)
    except User.DoesNotExist:
        try:
            target = User.objects.get(matri_id=matri_id)
        except User.DoesNotExist:
            return None, Response({
                'success': False,
                'error': {'code': 404, 'message': 'Profile not found.'},
            }, status=status.HTTP_404_NOT_FOUND)
    return target, None


class BlockListCreateDeleteView(APIView):
    """
    GET    /api/v1/blocks/  — list profiles I blocked
    POST   /api/v1/blocks/  — block { matri_id }
    DELETE /api/v1/blocks/  — unblock { matri_id }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        target, err = _resolve_target(request.data.get('matri_id') if isinstance(request.data, dict) else None)
        if err:
            return err
        if target.pk == request.user.pk:
            return Response({
                'success': False,
                'error': {'code': 403, 'message': 'Cannot block your own profile.'},
            }, status=status.HTTP_403_FORBIDDEN)

        created = False
        try:
            _, created = UserBlock.objects.get_or_create(
                blocker=request.user,
                blocked=target,
            )
        except IntegrityError:
            created = False

        # Clear wishlist both directions between the pair
        Wishlist.objects.filter(
            Q(user=request.user, profile=target) | Q(user=target, profile=request.user)
        ).delete()

        return Response({
            'success': True,
            'data': {
                'matri_id': target.matri_id,
                'is_blocked': True,
            },
            'message': 'User blocked.' if created else 'User already blocked.',
        }, status=status.HTTP_200_OK)

    def delete(self, request):
        matri_id = None
        if isinstance(request.data, dict):
            matri_id = request.data.get('matri_id')
        if not matri_id:
            matri_id = request.query_params.get('matri_id')
        target, err = _resolve_target(matri_id)
        if err:
            return err

        deleted, _ = UserBlock.objects.filter(
            blocker=request.user,
            blocked=target,
        ).delete()

        return Response({
            'success': True,
            'data': {
                'matri_id': target.matri_id,
                'is_blocked': False,
            },
            'message': 'User unblocked.' if deleted else 'User was not blocked.',
        }, status=status.HTTP_200_OK)

    def get(self, request):
        page, page_size = _parse_page_params(request, default_page_size=10, max_page_size=50)

        _profile_related = (
            'blocked',
            'blocked__user_religion', 'blocked__user_religion__religion', 'blocked__user_religion__caste_fk',
            'blocked__user_personal', 'blocked__user_personal__height', 'blocked__user_personal__marital_status',
            'blocked__user_education', 'blocked__user_education__highest_education', 'blocked__user_education__occupation',
            'blocked__user_location', 'blocked__user_location__state', 'blocked__user_location__city',
            'blocked__user_photos',
        )
        qs = (
            UserBlock.objects.filter(blocker=request.user)
            .select_related(*_profile_related)
            .order_by('-created_at')
        )
        total = qs.count()
        start = (page - 1) * page_size
        page_qs = qs[start:start + page_size]

        viewer = (
            User.objects.filter(pk=request.user.pk)
            .select_related(
                'user_religion', 'user_religion__religion', 'user_religion__caste_fk',
                'user_personal', 'user_personal__height', 'user_personal__marital_status',
                'user_education', 'user_education__highest_education', 'user_education__occupation',
                'user_location', 'user_location__state', 'user_location__city',
            )
            .first()
        ) or request.user
        viewer_rel = _safe_one_to_one(viewer, 'user_religion')
        viewer_pers = _safe_one_to_one(viewer, 'user_personal')
        viewer_edu = _safe_one_to_one(viewer, 'user_education')
        viewer_loc = _safe_one_to_one(viewer, 'user_location')

        profiles = []
        for item in page_qs:
            u = item.blocked
            rel = _safe_one_to_one(u, 'user_religion')
            pers = _safe_one_to_one(u, 'user_personal')
            edu = _safe_one_to_one(u, 'user_education')
            loc = _safe_one_to_one(u, 'user_location')

            match_pct = compute_match_percentage(
                viewer, u,
                viewer_rel, viewer_pers, viewer_edu, viewer_loc,
                rel, pers, edu, loc,
            )
            data = _build_wishlist_profile_dict(viewer, u, request=request)
            data['match_percentage'] = match_pct
            profiles.append(data)

        ser = BlockedProfileSerializer(profiles, many=True)
        return Response({
            'success': True,
            'data': {
                'total': total,
                'page': page,
                'page_size': page_size,
                'limit': page_size,
                'profiles': ser.data,
            },
        }, status=status.HTTP_200_OK)
