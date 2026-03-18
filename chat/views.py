"""
REST APIs for chat list and message history.
"""
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from plans.models import Conversation, Message
from plans.services import has_accepted_interest_between
from profiles.models import UserPhotos
from matches.serializers import format_last_seen
from core.media import absolute_media_url


def _other_user(conv, current_user):
    return conv.user2 if current_user.pk == conv.user1_id else conv.user1


def _profile_photo_url(request, user):
    try:
        photos = user.user_photos
        if photos and photos.profile_photo:
            return absolute_media_url(request, photos.profile_photo)
    except Exception:
        pass
    return None


class ChatListView(APIView):
    """
    GET /api/v1/chat/list/
    Returns conversations for the current user with last message and unread count.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        convs = (
            Conversation.objects.filter(
                Q(user1=user) | Q(user2=user)
            )
            .select_related('user1', 'user2')
            .order_by('-updated_at')
        )
        out = []
        for conv in convs:
            other = _other_user(conv, user)
            # Hide conversations if interest was not accepted (defense-in-depth).
            if not has_accepted_interest_between(user, other):
                continue
            last_msg = conv.messages.order_by('-created_at').first()
            unread = Message.objects.filter(
                conversation=conv
            ).exclude(sender=user).filter(read_at__isnull=True).count()
            out.append({
                'conversation_id': conv.id,
                'other_user': {
                    'matri_id': other.matri_id or '',
                    'name': other.name or '',
                    'profile_photo': _profile_photo_url(request, other),
                    'is_online': bool(getattr(other, "last_seen", None) and (timezone.now() - getattr(other, "last_seen")) < timezone.timedelta(minutes=15)),
                },
                'last_message': {
                    'preview': (last_msg.text[:80] + '...') if last_msg and len(last_msg.text) > 80 else (last_msg.text if last_msg else None),
                    'timestamp': last_msg.created_at.isoformat() if last_msg else None,
                },
                'unread_count': unread,
                'updated_at': conv.updated_at.isoformat() if conv.updated_at else None,
            })
        return Response({
            'success': True,
            'data': {
                'conversations': out,
            },
        }, status=status.HTTP_200_OK)


class ChatMessagesView(APIView):
    """
    GET /api/v1/chat/messages/<conversation_id>/
    Returns paginated messages for a conversation. User must be a participant.
    Optional: ?page=1&limit=20
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id):
        user = request.user
        try:
            conv = Conversation.objects.select_related('user1', 'user2').get(pk=conversation_id)
        except Conversation.DoesNotExist:
            return Response({
                'success': False,
                'error': {'code': 404, 'message': 'Conversation not found.'},
            }, status=status.HTTP_404_NOT_FOUND)
        if user.pk != conv.user1_id and user.pk != conv.user2_id:
            return Response({
                'success': False,
                'error': {'code': 403, 'message': 'Not a participant in this conversation.'},
            }, status=status.HTTP_403_FORBIDDEN)

        other = _other_user(conv, user)
        if not has_accepted_interest_between(user, other):
            return Response({
                'success': False,
                'error': {'code': 403, 'message': 'Please accept the interest request to view messages.'},
            }, status=status.HTTP_403_FORBIDDEN)

        # Mark all messages from the other user as read when this user
        # loads the conversation, so unread_count in the chat list stays in sync.
        Message.objects.filter(
            conversation=conv,
            read_at__isnull=True
        ).exclude(sender=user).update(read_at=timezone.now())

        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            limit = max(1, min(100, int(request.query_params.get('limit', 20))))
        except (TypeError, ValueError):
            limit = 20
        qs = Message.objects.filter(conversation=conv).select_related('sender').order_by('-created_at')
        total = qs.count()
        start = (page - 1) * limit
        msgs = qs[start:start + limit]
        results = [
            {
                'id': m.id,
                'sender_id': m.sender_id,
                'sender_matri_id': m.sender.matri_id or '',
                'sender_name': m.sender.name or '',
                'text': m.text,
                'created_at': m.created_at.isoformat(),
                'read_at': m.read_at.isoformat() if m.read_at else None,
            }
            for m in reversed(list(msgs))
        ]

        # Online status for the other participant (same 15-min rule + formatted last_seen)
        other = _other_user(conv, user)
        last_seen = getattr(other, "last_seen", None)
        is_online = bool(last_seen and (timezone.now() - last_seen) < timezone.timedelta(minutes=15))

        return Response({
            'success': True,
            'data': {
                'conversation_id': conv.id,
                'other_user': {
                    'matri_id': other.matri_id or '',
                    'name': other.name or '',
                    'profile_photo': _profile_photo_url(request, other),
                    'is_online': is_online,
                    'last_seen': format_last_seen(last_seen) if last_seen else None,
                },
                'total': total,
                'page': page,
                'limit': limit,
                'messages': results,
            },
        }, status=status.HTTP_200_OK)


class ChatUserStatusView(APIView):
    """
    GET /api/v1/chat/status/<matri_id>/
    Returns whether the given user is online (based on last_seen within 15 minutes).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, matri_id):
        try:
            user = User.objects.get(matri_id=matri_id, is_active=True)
        except User.DoesNotExist:
            return Response({
                'success': False,
                'error': {'code': 404, 'message': 'User not found.'},
            }, status=status.HTTP_404_NOT_FOUND)

        from datetime import timedelta
        now = timezone.now()
        last_seen = getattr(user, 'last_seen', None)
        is_online = bool(last_seen and last_seen >= now - timedelta(minutes=15))

        return Response({
            'success': True,
            'data': {
                'matri_id': user.matri_id or '',
                'is_online': is_online,
                'last_seen': last_seen.isoformat() if last_seen else None,
            },
        }, status=status.HTTP_200_OK)
