"""
Liveness / readiness health checks for load balancers and Docker.
Additive endpoint — does not change existing API routes.
"""
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views import View


class HealthCheckView(View):
    """
    GET /health/
    Returns 200 when DB and Redis respond; 503 otherwise.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        checks = {'database': False, 'redis': False}
        try:
            connection.ensure_connection()
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
            checks['database'] = True
        except Exception:
            checks['database'] = False

        try:
            cache.set('healthcheck:ping', '1', 5)
            checks['redis'] = cache.get('healthcheck:ping') == '1'
        except Exception:
            checks['redis'] = False

        ok = all(checks.values())
        return JsonResponse(
            {'status': 'ok' if ok else 'degraded', 'checks': checks},
            status=200 if ok else 503,
        )
