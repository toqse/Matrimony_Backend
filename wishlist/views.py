from django.db import IntegrityError
from django.db.models import Q
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from django.core.exceptions import ObjectDoesNotExist

from accounts.models import User
from matches.utils import compute_match_percentage
from .models import Wishlist
from .serializers import WishlistProfileSerializer, _build_wishlist_profile_dict


def _safe_one_to_one(obj, rel_name):
    """Return related OneToOne object or None without raising DoesNotExist."""
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


class WishlistToggleView(APIView):
    """
    POST /api/v1/wishlist/toggle/
    Body: { "matri_id": "AM100012" }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        matri_id = (request.data.get('matri_id') or '').strip()
        if not matri_id:
            return Response({
                'success': False,
                'error': {'code': 400, 'message': 'matri_id is required.'},
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            profile_user = User.objects.get(matri_id=matri_id, is_active=True)
        except User.DoesNotExist:
            return Response({
                'success': False,
                'error': {'code': 404, 'message': 'Profile not found.'},
            }, status=status.HTTP_404_NOT_FOUND)

        if profile_user.pk == request.user.pk:
            return Response({
                'success': False,
                'error': {'code': 403, 'message': 'Cannot wishlist your own profile.'},
            }, status=status.HTTP_403_FORBIDDEN)

        wishlist_qs = Wishlist.objects.filter(user=request.user, profile=profile_user)
        if wishlist_qs.exists():
            wishlist_qs.delete()
            is_wishlisted = False
        else:
            try:
                Wishlist.objects.create(user=request.user, profile=profile_user)
            except IntegrityError:
                # Unique constraint safety net; treat as wishlisted.
                pass
            is_wishlisted = True

        return Response({
            'success': True,
            'data': {'is_wishlisted': is_wishlisted},
        }, status=status.HTTP_200_OK)


class WishlistListView(APIView):
    """
    GET /api/v1/wishlist/
    Query params: page (default 1), page_size (default 10), limit alias supported
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        page, page_size = _parse_page_params(request, default_page_size=10, max_page_size=50)

        _profile_related = (
            'profile',
            'profile__user_religion', 'profile__user_religion__religion', 'profile__user_religion__caste_fk',
            'profile__user_personal', 'profile__user_personal__height', 'profile__user_personal__marital_status',
            'profile__user_education', 'profile__user_education__highest_education', 'profile__user_education__occupation',
            'profile__user_location', 'profile__user_location__state', 'profile__user_location__city',
            'profile__user_photos',
        )
        qs = (
            Wishlist.objects.filter(user=request.user)
            .select_related(*_profile_related)
            .order_by('-created_at')
        )
        total = qs.count()
        start = (page - 1) * page_size
        page_qs = qs[start:start + page_size]

        # Preload viewer profile objects for match percentage computation (one query each, not per row)
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
            u = item.profile
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

        ser = WishlistProfileSerializer(profiles, many=True)

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


class WishlistRemoveView(APIView):
    """
    POST /api/v1/wishlist/remove/
    Body: { "matri_id": "AM100012" }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        matri_id = (request.data.get('matri_id') or '').strip()
        if not matri_id:
            return Response({
                'success': False,
                'error': {'code': 400, 'message': 'matri_id is required.'},
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            profile_user = User.objects.get(matri_id=matri_id, is_active=True)
        except User.DoesNotExist:
            return Response({
                'success': False,
                'error': {'code': 404, 'message': 'Profile not found.'},
            }, status=status.HTTP_404_NOT_FOUND)

        Wishlist.objects.filter(user=request.user, profile=profile_user).delete()

        return Response({
            'success': True,
            'message': 'Profile removed from wishlist.',
        }, status=status.HTTP_200_OK)

