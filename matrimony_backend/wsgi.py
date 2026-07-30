"""
WSGI config for matrimony_backend project.

/health/live/ is answered here before Django middleware so we can isolate
Gunicorn/Docker hangs from application-stack hangs.
"""
import os
import sys

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'matrimony_backend.settings')

_django_app = get_wsgi_application()


def application(environ, start_response):
    path = environ.get('PATH_INFO') or ''
    # Zero-dependency liveness: no Django middleware, DB, Redis, or views.
    if path == '/health/live/' or path == '/health/live':
        print('wsgi: /health/live/ short-circuit', file=sys.stderr, flush=True)
        body = b'{"status":"alive","via":"wsgi"}\n'
        start_response(
            '200 OK',
            [
                ('Content-Type', 'application/json'),
                ('Content-Length', str(len(body))),
                ('Cache-Control', 'no-store'),
            ],
        )
        return [body]

    if path.startswith('/health'):
        print(f'wsgi: pass-through to Django path={path!r}', file=sys.stderr, flush=True)

    return _django_app(environ, start_response)
