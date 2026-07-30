"""
Liveness / readiness health checks for load balancers and Docker.
Additive endpoint — does not change existing API routes.

Must always return within a bounded time (client socket timeouts on DB/Redis).
Healthy → 200; failed dependency → 503; never hang indefinitely.
"""
import logging

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views import View

logger = logging.getLogger('core.health')


def _health_debug(message: str) -> None:
    if getattr(settings, 'HEALTH_DEBUG_LOG', False):
        logger.info(message)


class HealthCheckView(View):
    """
    GET /health/
    Returns 200 when DB and Redis respond; 503 otherwise.
    Each dependency check is isolated so timeouts/exceptions become false checks,
    not an infinite hang (requires bounded Redis/MySQL client timeouts in settings).
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        checks = {'database': False, 'redis': False}

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
            _health_debug('health: before cache.set')
            cache.set('healthcheck:ping', '1', 5)
            _health_debug('health: after cache.set')
            _health_debug('health: before cache.get')
            checks['redis'] = cache.get('healthcheck:ping') == '1'
            _health_debug(f'health: after cache.get redis_ok={checks["redis"]}')
        except Exception as exc:
            _health_debug(f'health: redis check failed: {exc!r}')
            checks['redis'] = False

        ok = all(checks.values())
        return JsonResponse(
            {'status': 'ok' if ok else 'degraded', 'checks': checks},
            status=200 if ok else 503,
        )
