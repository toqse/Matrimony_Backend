"""
Profile Settings APIs: GET profile, PATCH visibility, interest permission, notifications, account, change-password.
"""
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.models import User
from plans.services import _get_user_plan
from profiles.models import UserLocation, UserPhotos
from .models import UserSettings
from .serializers import (
    ProfileVisibilitySerializer,
    InterestPermissionSerializer,
    NotificationSettingsSerializer,
    AccountUpdateSerializer,
    ChangePasswordSerializer,
)


def _get_or_create_settings(user):
    try:
        settings_obj = UserSettings.objects.get(user=user)
    except UserSettings.DoesNotExist:
        settings_obj = UserSettings.objects.create(user=user)
    return settings_obj


def _plan_display_name(user):
    up = _get_user_plan(user)
    if up and getattr(up, 'plan', None):
        return up.plan.name or 'Free'
    return 'Free'


def _location_display(user):
    try:
        loc = UserLocation.objects.filter(user=user).first()
    except Exception:
        return None
    if not loc:
        return None
    parts = []
    city = getattr(getattr(loc, 'city', None), 'name', None)
    state = getattr(getattr(loc, 'state', None), 'name', None)
    country = getattr(getattr(loc, 'country', None), 'name', None)
    if city:
        parts.append(city)
    if state:
        parts.append(state)
    if country:
        parts.append(country)
    return ', '.join(parts) if parts else None


def _profile_photo_url(user):
    try:
        photos = UserPhotos.objects.filter(user=user).first()
        if photos and photos.profile_photo:
            return photos.profile_photo.url if hasattr(photos.profile_photo, 'url') else str(photos.profile_photo)
    except Exception:
        pass
    return None


class ProfileSettingsView(APIView):
    """GET /api/v1/settings/profile/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        settings_obj = _get_or_create_settings(user)
        return Response({
            'success': True,
            'data': {
                'name': user.name or '',
                'matri_id': user.matri_id or '',
                'profile_photo': _profile_photo_url(user),
                'location': _location_display(user) or '',
                'plan': _plan_display_name(user),
                'profile_visibility': settings_obj.profile_visibility,
                'interest_permission': settings_obj.interest_request_permission,
                'notifications': {
                    'interest_request': settings_obj.notify_interest,
                    'chat': settings_obj.notify_chat,
                    'profile_views': settings_obj.notify_profile_views,
                    'new_matches': settings_obj.notify_new_matches,
                },
            },
        }, status=status.HTTP_200_OK)


class ProfileVisibilityView(APIView):
    """PATCH /api/v1/settings/profile-visibility/"""
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        ser = ProfileVisibilitySerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        settings_obj = _get_or_create_settings(request.user)
        settings_obj.profile_visibility = ser.validated_data['profile_visibility']
        settings_obj.save(update_fields=['profile_visibility', 'updated_at'])
        return Response({
            'success': True,
            'message': 'Profile visibility updated.',
        }, status=status.HTTP_200_OK)


class InterestPermissionView(APIView):
    """PATCH /api/v1/settings/interest-permission/"""
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        ser = InterestPermissionSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        settings_obj = _get_or_create_settings(request.user)
        settings_obj.interest_request_permission = ser.validated_data['interest_permission']
        settings_obj.save(update_fields=['interest_request_permission', 'updated_at'])
        return Response({
            'success': True,
            'message': 'Interest permission updated.',
        }, status=status.HTTP_200_OK)


class NotificationSettingsView(APIView):
    """PATCH /api/v1/settings/notifications/"""
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        ser = NotificationSettingsSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        settings_obj = _get_or_create_settings(request.user)
        if 'interest_request' in ser.validated_data:
            settings_obj.notify_interest = ser.validated_data['interest_request']
        if 'chat' in ser.validated_data:
            settings_obj.notify_chat = ser.validated_data['chat']
        if 'profile_views' in ser.validated_data:
            settings_obj.notify_profile_views = ser.validated_data['profile_views']
        if 'new_matches' in ser.validated_data:
            settings_obj.notify_new_matches = ser.validated_data['new_matches']
        settings_obj.save(update_fields=[
            'notify_interest', 'notify_chat', 'notify_profile_views', 'notify_new_matches', 'updated_at',
        ])
        return Response({
            'success': True,
            'message': 'Notification settings updated.',
        }, status=status.HTTP_200_OK)


class AccountUpdateView(APIView):
    """PATCH /api/v1/settings/account/"""
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        ser = AccountUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        user = request.user
        if 'name' in ser.validated_data:
            user.name = ser.validated_data['name']
        if 'email' in ser.validated_data:
            email = (ser.validated_data['email'] or '').strip().lower() or None
            if email and User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                return Response({
                    'success': False,
                    'error': {'code': 400, 'message': 'Email already in use by another account.'},
                }, status=status.HTTP_400_BAD_REQUEST)
            user.email = email
        if 'phone_number' in ser.validated_data:
            phone = (ser.validated_data['phone_number'] or '').strip()
            if phone and User.objects.filter(mobile=phone).exclude(pk=user.pk).exists():
                return Response({
                    'success': False,
                    'error': {'code': 400, 'message': 'Phone number already in use by another account.'},
                }, status=status.HTTP_400_BAD_REQUEST)
            user.mobile = phone
        user.save(update_fields=['name', 'email', 'mobile', 'updated_at'])
        return Response({
            'success': True,
            'message': 'Account details updated.',
        }, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    """POST /api/v1/settings/change-password/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = ChangePasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(ser.validated_data['current_password']):
            return Response({
                'success': False,
                'error': {'code': 400, 'message': 'Current password is incorrect.'},
            }, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(ser.validated_data['new_password'])
        user.save(update_fields=['password', 'updated_at'])
        return Response({
            'success': True,
            'message': 'Password changed successfully.',
        }, status=status.HTTP_200_OK)
