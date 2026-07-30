"""
Liveness / readiness health checks for load balancers and Docker.
Additive endpoint — does not change existing API routes.

Must always return within a bounded time.
Healthy → 200; failed dependency → 503; never hang indefinitely.
"""
import logging
import sys
from urllib.parse import urlparse

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views import View

logger = logging.getLogger('core.health')


def _health_debug(message: str) -> None:
    """Emit to logger and stderr so docker logs show the stall point."""
    if not getattr(settings, 'HEALTH_DEBUG_LOG', False):
        return
    logger.info(message)
    print(message, file=sys.stderr, flush=True)


def _redis_ping_ok() -> bool:
    """
    Protocol PING with explicit socket timeouts (bypasses django_redis).
    An open TCP port is not enough; this matches wait-for-redis.sh.
    """
    import redis

    url = getattr(settings, 'CACHE_REDIS_URL', None) or getattr(
        settings, 'REDIS_URL', 'redis://localhost:6379/0'
    )
    connect_timeout = float(getattr(settings, 'REDIS_SOCKET_CONNECT_TIMEOUT', 2) or 2)
    socket_timeout = float(getattr(settings, 'REDIS_SOCKET_TIMEOUT', 2) or 2)
    u = urlparse(url)
    host = u.hostname or 'localhost'
    port = int(u.port or 6379)
    password = u.password
    db = 0
    if u.path and u.path.strip('/'):
        try:
            db = int(u.path.strip('/').split('/')[0])
        except ValueError:
            db = 0
    client = redis.Redis(
        host=host,
        port=port,
        password=password,
        db=db,
        socket_connect_timeout=connect_timeout,
        socket_timeout=socket_timeout,
    )
    return bool(client.ping())


class HealthLiveView(View):
    """
    GET /health/live/
    Process liveness only — no DB, no Redis, no external I/O.
    Must return immediately. Use to isolate middleware/Gunicorn hangs
    from dependency hangs on /health/.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        _health_debug('health/live: entered')
        return JsonResponse({'status': 'alive'}, status=200)


class HealthCheckView(View):
    """
    GET /health/
    Readiness: 200 when DB and Redis respond; 503 otherwise.
    Each check is isolated and time-bounded (MySQL OPTIONS + Redis socket timeouts).
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        checks = {'database': False, 'redis': False}
        _health_debug('health: request entered HealthCheckView.get')

        try:
            _health_debug('health: before ensure_connection')
            connection.ensure_connection()
            _health_debug('health: after ensure_connection')
            _health_debug('health: before SELECT 1')
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
            _health_debug('health: after SELECT 1')
            checks['database'] = True
        except Exception as exc:
            _health_debug(f'health: database check failed: {exc!r}')
            checks['database'] = False

        try:
            _health_debug('health: before redis PING')
            checks['redis'] = _redis_ping_ok()
            _health_debug(f'health: after redis PING redis_ok={checks["redis"]}')
        except Exception as exc:
            _health_debug(f'health: redis check failed: {exc!r}')
            checks['redis'] = False

        ok = all(checks.values())
        _health_debug(f'health: returning status={"ok" if ok else "degraded"}')
        return JsonResponse(
            {'status': 'ok' if ok else 'degraded', 'checks': checks},
            status=200 if ok else 503,
        )
