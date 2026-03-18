"""
ASGI config for matrimony_backend project.
HTTP -> Django; WebSocket -> JWT auth + chat consumer.
"""
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'matrimony_backend.settings')

# First, initialize Django and load apps.
django_asgi_app = get_asgi_application()

# Import middleware and routing only after Django apps are ready.
from chat.middleware import JWTAuthMiddleware  # noqa: E402
from chat.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        JWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
    ),
})
