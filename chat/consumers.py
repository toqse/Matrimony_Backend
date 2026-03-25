"""
WebSocket consumer for real-time chat.
Route: ws/chat/<conversation_id>/
"""
import json
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

from plans.models import Conversation, Message
from plans.services import has_accepted_interest_between, user_has_active_plan

from core.last_seen import touch_user_last_seen, mark_user_offline


@database_sync_to_async
def _viewer_has_active_plan(user):
    return user_has_active_plan(user)


class ChatConsumer(AsyncWebsocketConsumer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conversation_id = None
        self.room_group_name = None

    @database_sync_to_async
    def get_conversation_and_verify(self, conversation_id, user):
        """Return (conversation, error_message). error_message is None if allowed."""
        if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
            return None, 'Authentication required'
        try:
            conv = Conversation.objects.get(pk=conversation_id)
        except Conversation.DoesNotExist:
            return None, 'Conversation not found'
        if user.pk != conv.user1_id and user.pk != conv.user2_id:
            return None, 'Not a participant'
        if not user_has_active_plan(user):
            return None, 'Active plan required'
        other = conv.user2 if user.pk == conv.user1_id else conv.user1
        if not has_accepted_interest_between(user, other):
            return None, 'Interest not accepted'
        return conv, None

    @database_sync_to_async
    def _peer_presence_payload(self, conv, current_user):
        """matri_id + is_online for the other participant (15-min last_seen rule)."""
        other = (
            conv.user2
            if current_user.pk == conv.user1_id
            else conv.user1
        )
        last = getattr(other, 'last_seen', None)
        online = bool(
            last and (timezone.now() - last) < timezone.timedelta(minutes=15)
        )
        return {
            'matri_id': getattr(other, 'matri_id', '') or '',
            'online': online,
        }

    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        user = self.scope.get('user')
        conv, err = await self.get_conversation_and_verify(self.conversation_id, user)
        if err or not conv:
            await self.close(code=4403)
            return
        # Mark existing unread messages from the other user as read when
        # this user opens the WebSocket for this conversation.
        await self.mark_messages_read_for_user(conv, user)
        self.room_group_name = f'chat_{self.conversation_id}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        # So the other participant sees this user as online (REST uses last_seen).
        await self._touch_last_seen(user.pk, force=True)
        matri_id = getattr(user, 'matri_id', '') or ''
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_presence',
                'matri_id': matri_id,
                'online': True,
            },
        )
        peer = await self._peer_presence_payload(conv, user)
        if peer.get('matri_id'):
            await self.send(
                text_data=json.dumps({
                    'type': 'presence',
                    'matri_id': peer['matri_id'],
                    'online': peer['online'],
                })
            )

    @database_sync_to_async
    def _touch_last_seen(self, user_pk, *, force=False, min_interval_seconds=45):
        touch_user_last_seen(
            user_pk, force=force, min_interval_seconds=min_interval_seconds
        )

    @database_sync_to_async
    def mark_messages_read_for_user(self, conv, user):
        """Mark all messages from the other user as read when user connects via WebSocket."""
        if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
            return
        Message.objects.filter(
            conversation=conv,
            read_at__isnull=True
        ).exclude(sender=user).update(read_at=timezone.now())

    async def disconnect(self, close_code):
        # Notify the other participant immediately (real-time Offline) and
        # move last_seen outside the 15-min "online" window.
        user = self.scope.get('user')
        try:
            if user and getattr(user, 'is_authenticated', False) and getattr(user, 'matri_id', None):
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_presence',
                        'matri_id': user.matri_id,
                        'online': False,
                    },
                )
                # Force last_seen out of the window so REST refetch shows Offline quickly.
                await database_sync_to_async(mark_user_offline)(user.pk)
        except Exception:
            pass
        if self.room_group_name:
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    @database_sync_to_async
    def save_message_and_touch_conversation(self, sender_id, text):
        """Save message, update conversation.updated_at; return (msg_id, created_at_iso)."""
        conv = Conversation.objects.get(pk=self.conversation_id)
        msg = Message.objects.create(
            conversation=conv,
            sender_id=sender_id,
            text=text,
        )
        conv.updated_at = timezone.now()
        conv.save(update_fields=['updated_at'])
        return msg.id, msg.created_at.isoformat()

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        user = self.scope.get('user')
        if not user or not getattr(user, 'is_authenticated', False) or not user.is_authenticated:
            await self.send(text_data=json.dumps({'error': 'Authentication required'}))
            return
        if not await _viewer_has_active_plan(user):
            await self.send(text_data=json.dumps({'error': 'Active plan required'}))
            return
        try:
            data = json.loads(text_data)
            text = (data.get('message') or data.get('text') or '').strip()
        except (json.JSONDecodeError, TypeError):
            await self.send(text_data=json.dumps({'error': 'Invalid JSON'}))
            return
        if not text:
            await self.send(text_data=json.dumps({'error': 'Message text required'}))
            return
        msg_id, created_at = await self.save_message_and_touch_conversation(user.pk, text)
        await self._touch_last_seen(user.pk, min_interval_seconds=30)
        payload = {
            'type': 'chat_message',
            'message_id': msg_id,
            # Cast UUID primary key to string so Redis/msgpack can serialize it
            'sender_id': str(user.pk),
            'sender_matri_id': getattr(user, 'matri_id', None) or '',
            'sender_name': getattr(user, 'name', None) or '',
            'text': text,
            'created_at': created_at,
        }
        await self.channel_layer.group_send(
            self.room_group_name,
            payload,
        )

    async def chat_message(self, event):
        """Receive broadcast from group and send to WebSocket."""
        await self.send(text_data=json.dumps({
            'message_id': event['message_id'],
            'sender_id': event['sender_id'],
            'sender_matri_id': event['sender_matri_id'],
            'sender_name': event['sender_name'],
            'text': event['text'],
            'created_at': event['created_at'],
        }))

    async def chat_presence(self, event):
        """Peer opened chat WebSocket — notify other participant (real-time Online)."""
        me = self.scope.get('user')
        if not me:
            return
        if (event.get('matri_id') or '') == (getattr(me, 'matri_id', None) or ''):
            return
        await self.send(
            text_data=json.dumps({
                'type': 'presence',
                'matri_id': event['matri_id'],
                'online': bool(event.get('online', True)),
            })
        )
