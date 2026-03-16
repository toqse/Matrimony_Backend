"""
JWT authentication for WebSocket connections.
Token can be passed as query string: ws://host/ws/chat/1/?token=<access_token>
"""
from urllib.parse import parse_qs
from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken


def get_user_from_scope(scope):
    """Extract and validate JWT from scope query_string; return User or AnonymousUser."""
    query_string = scope.get('query_string', b'').decode('utf-8')
    params = parse_qs(query_string)
    token_list = params.get('token') or params.get('access') or []
    token = token_list[0] if token_list else None
    if not token:
        return AnonymousUser()
    try:
        access = AccessToken(token)
        user_id = access.get('user_id')
        if not user_id:
            return AnonymousUser()
    except (InvalidToken, Exception):
        return AnonymousUser()
    from accounts.models import User
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return AnonymousUser()


class JWTAuthMiddleware:
    """
    Custom ASGI middleware that sets scope['user'] from JWT in query string.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'websocket':
            scope['user'] = await sync_to_async(get_user_from_scope)(scope)
        return await self.app(scope, receive, send)
