from django.db import IntegrityError
from django.db.models import Q
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.models import User
from matches.utils import compute_match_percentage
from profiles.models import UserReligion, UserPersonal, UserEducation, UserLocation
from .models import Wishlist
from .serializers import WishlistProfileSerializer, _build_wishlist_profile_dict


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
    Query params: page (default 1), limit (default 10)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            limit = max(1, min(50, int(request.query_params.get('limit', 10))))
        except (TypeError, ValueError):
            limit = 10

        qs = Wishlist.objects.filter(user=request.user).select_related('profile').order_by('-created_at')
        total = qs.count()
        start = (page - 1) * limit
        page_qs = qs[start:start + limit]

        # Preload viewer profile objects for match percentage computation
        viewer = request.user
        viewer_rel = getattr(viewer, 'user_religion', None) or UserReligion.objects.filter(user=viewer).select_related(
            'religion', 'caste_fk'
        ).first()
        viewer_pers = getattr(viewer, 'user_personal', None) or UserPersonal.objects.filter(user=viewer).select_related(
            'height', 'marital_status'
        ).first()
        viewer_edu = getattr(viewer, 'user_education', None) or UserEducation.objects.filter(user=viewer).select_related(
            'highest_education', 'occupation'
        ).first()
        viewer_loc = getattr(viewer, 'user_location', None) or UserLocation.objects.filter(user=viewer).select_related(
            'state', 'city'
        ).first()

        profiles = []
        for item in page_qs:
            u = item.profile
            rel = getattr(u, 'user_religion', None) or UserReligion.objects.filter(user=u).select_related(
                'religion', 'caste_fk'
            ).first()
            pers = getattr(u, 'user_personal', None) or UserPersonal.objects.filter(user=u).select_related(
                'height', 'marital_status'
            ).first()
            edu = getattr(u, 'user_education', None) or UserEducation.objects.filter(user=u).select_related(
                'highest_education', 'occupation'
            ).first()
            loc = getattr(u, 'user_location', None) or UserLocation.objects.filter(user=u).select_related(
                'state', 'city'
            ).first()

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
                'limit': limit,
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

