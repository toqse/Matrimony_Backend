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
        return conv, None

    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        user = self.scope.get('user')
        conv, err = await self.get_conversation_and_verify(self.conversation_id, user)
        if err or not conv:
            await self.close(code=4403)
            return
        self.room_group_name = f'chat_{self.conversation_id}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
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
        payload = {
            'type': 'chat_message',
            'message_id': msg_id,
            'sender_id': user.pk,
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
