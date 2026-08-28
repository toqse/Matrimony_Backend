"""
REST APIs for chat list and message history.
"""
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Count, F, IntegerField, OuterRef, Q, Subquery, Case, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from core.media import absolute_media_url
from matches.serializers import format_last_seen
from plans.models import Conversation, Interest, Message
from plans.services import get_user_plan_status, has_accepted_interest_between, plan_expired_response


def _parse_page_params(request, default_page_size=20, max_page_size=100):
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


def _is_online(user):
    last_seen = getattr(user, 'last_seen', None)
    if not last_seen:
        return False
    return (timezone.now() - last_seen) < timedelta(minutes=15)


def _accepted_other_user_ids_subquery(user):
    """Subquery of counterparties with an accepted interest (either direction)."""
    return (
        Interest.objects.filter(status=Interest.STATUS_ACCEPTED)
        .filter(Q(sender=user) | Q(receiver=user))
        .annotate(
            other_id=Case(
                When(sender=user, then=F('receiver_id')),
                default=F('sender_id'),
            )
        )
        .values('other_id')
    )


def _serialize_message(m):
    return {
        'id': m.id,
        'sender_id': str(m.sender_id),
        'sender_matri_id': m.sender.matri_id or '',
        'sender_name': m.sender.name or '',
        'text': m.text,
        'created_at': m.created_at.isoformat() if m.created_at else None,
        'read_at': m.read_at.isoformat() if m.read_at else None,
    }


def _participant_error_response(request, conversation_id):
    """
    Load conversation and verify the current user may use it.

    Returns (conv, other, None) on success, or (None, None, Response) on failure.
    """
    user = request.user
    if get_user_plan_status(user) != 'active':
        return None, None, Response(
            plan_expired_response(user), status=status.HTTP_403_FORBIDDEN
        )
    try:
        conv = Conversation.objects.select_related('user1', 'user2').get(
            pk=conversation_id
        )
    except Conversation.DoesNotExist:
        return None, None, Response(
            {
                'success': False,
                'error': {'code': 404, 'message': 'Conversation not found.'},
            },
            status=status.HTTP_404_NOT_FOUND,
        )
    if user.pk != conv.user1_id and user.pk != conv.user2_id:
        return None, None, Response(
            {
                'success': False,
                'error': {
                    'code': 403,
                    'message': 'Not a participant in this conversation.',
                },
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    other = _other_user(conv, user)
    if not has_accepted_interest_between(user, other):
        return None, None, Response(
            {
                'success': False,
                'error': {
                    'code': 403,
                    'message': 'Please accept the interest request to view messages.',
                },
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return conv, other, None


def _broadcast_chat_message(*, conversation_id, user, msg):
    """Notify WebSocket clients; must not fail the REST write if Redis is down."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    payload = {
        'type': 'chat_message',
        'message_id': msg.id,
        'sender_id': str(user.pk),
        'sender_matri_id': getattr(user, 'matri_id', None) or '',
        'sender_name': getattr(user, 'name', None) or '',
        'text': msg.text,
        'created_at': msg.created_at.isoformat() if msg.created_at else None,
    }
    try:
        async_to_sync(channel_layer.group_send)(f'chat_{conversation_id}', payload)
    except Exception:
        pass


class ChatListView(APIView):
    """
    GET /api/v1/chat/list/
    Returns conversations for the current user with last message and unread count.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if get_user_plan_status(user) != 'active':
            return Response(plan_expired_response(user), status=status.HTTP_403_FORBIDDEN)
        page, page_size = _parse_page_params(request, default_page_size=20, max_page_size=100)

        accepted_others = _accepted_other_user_ids_subquery(user)
        last_text_qs = (
            Message.objects.filter(conversation_id=OuterRef('pk'))
            .order_by('-created_at', '-id')
        )
        last_at_qs = (
            Message.objects.filter(conversation_id=OuterRef('pk'))
            .order_by('-created_at', '-id')
        )
        unread_qs = (
            Message.objects.filter(
                conversation_id=OuterRef('pk'),
                read_at__isnull=True,
            )
            .exclude(sender_id=user.pk)
            .order_by()
            .values('conversation_id')
            .annotate(c=Count('id'))
            .values('c')
        )

        convs = (
            Conversation.objects.filter(Q(user1=user) | Q(user2=user))
            .filter(
                Q(user1=user, user2_id__in=Subquery(accepted_others))
                | Q(user2=user, user1_id__in=Subquery(accepted_others))
            )
            .select_related(
                'user1', 'user2',
                'user1__user_photos', 'user2__user_photos',
            )
            .annotate(
                last_msg_text=Subquery(last_text_qs.values('text')[:1]),
                last_msg_at=Subquery(last_at_qs.values('created_at')[:1]),
                unread_count=Coalesce(
                    Subquery(unread_qs, output_field=IntegerField()),
                    0,
                ),
            )
            .order_by('-updated_at')
        )

        total = convs.count()
        start = (page - 1) * page_size
        page_convs = list(convs[start:start + page_size])

        conversations = []
        for conv in page_convs:
            other = _other_user(conv, user)
            last_text = getattr(conv, 'last_msg_text', None)
            last_at = getattr(conv, 'last_msg_at', None)
            preview = None
            if last_text:
                preview = (last_text[:80] + '...') if len(last_text) > 80 else last_text
            conversations.append({
                'conversation_id': conv.id,
                'other_user': {
                    'matri_id': other.matri_id or '',
                    'name': other.name or '',
                    'profile_photo': _profile_photo_url(request, other),
                    'is_online': _is_online(other),
                },
                'last_message': {
                    'preview': preview,
                    'timestamp': last_at.isoformat() if last_at else None,
                },
                'unread_count': int(getattr(conv, 'unread_count', 0) or 0),
                'updated_at': conv.updated_at.isoformat() if conv.updated_at else None,
            })
        return Response({
            'success': True,
            'data': {
                'total': total,
                'page': page,
                'page_size': page_size,
                'limit': page_size,
                'conversations': conversations,
            },
        }, status=status.HTTP_200_OK)


class ChatMessagesView(APIView):
    """
    GET  /api/v1/chat/messages/<conversation_id>/
         Paginated messages. Page 1 is the newest window, ordered oldest→newest
         within the page so the last list preview is always included.
    POST /api/v1/chat/messages/<conversation_id>/
         Persist a message (WebSocket is live delivery only).
    Optional GET: ?page=1&limit=20
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def get(self, request, conversation_id):
        conv, other, err = _participant_error_response(request, conversation_id)
        if err:
            return err
        user = request.user

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

        qs = (
            Message.objects.filter(conversation=conv)
            .select_related('sender')
            .order_by('-created_at', '-id')
        )
        total = qs.count()
        start = (page - 1) * limit
        messages = list(qs[start:start + limit])
        messages.reverse()

        last_seen = getattr(other, 'last_seen', None)
        return Response({
            'success': True,
            'data': {
                'conversation_id': conv.id,
                'other_user': {
                    'matri_id': other.matri_id or '',
                    'name': other.name or '',
                    'profile_photo': _profile_photo_url(request, other),
                    'is_online': _is_online(other),
                    'last_seen': format_last_seen(last_seen) if last_seen else None,
                },
                'total': total,
                'page': page,
                'limit': limit,
                'messages': [_serialize_message(m) for m in messages],
            },
        }, status=status.HTTP_200_OK)

    def post(self, request, conversation_id):
        conv, _other, err = _participant_error_response(request, conversation_id)
        if err:
            return err
        user = request.user
        text = (
            (request.data.get('message') or request.data.get('text') or '')
            .strip()
            if isinstance(request.data, dict)
            else ''
        )
        if not text:
            return Response(
                {
                    'success': False,
                    'error': {'code': 400, 'message': 'Message text required.'},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        msg = Message.objects.create(
            conversation=conv,
            sender=user,
            text=text,
        )
        conv.updated_at = timezone.now()
        conv.save(update_fields=['updated_at'])
        msg.sender = user
        _broadcast_chat_message(conversation_id=conv.id, user=user, msg=msg)

        return Response(
            {
                'success': True,
                'data': _serialize_message(msg),
            },
            status=status.HTTP_201_CREATED,
        )


class ChatUserStatusView(APIView):
    """
    GET /api/v1/chat/status/<matri_id>/
    Returns online status for a single user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, matri_id):
        try:
            target = User.objects.get(matri_id=matri_id, is_active=True)
        except User.DoesNotExist:
            return Response({
                'success': False,
                'error': {'code': 404, 'message': 'Profile not found.'},
            }, status=status.HTTP_404_NOT_FOUND)

        last_seen = getattr(target, 'last_seen', None)
        return Response({
            'success': True,
            'data': {
                'matri_id': target.matri_id or '',
                'is_online': _is_online(target),
                'last_seen': format_last_seen(last_seen) if last_seen else None,
            },
        }, status=status.HTTP_200_OK)
