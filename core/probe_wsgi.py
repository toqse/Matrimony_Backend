"""
Minimal WSGI app with zero Django/Redis/DB imports.
Use temporarily to prove Gunicorn + Docker port publishing work:

  gunicorn core.probe_wsgi:application --bind 0.0.0.0:8000 --worker-class sync --workers 1
"""


def application(environ, start_response):
    path = environ.get('PATH_INFO') or ''
    body = ('{"status":"alive","via":"probe_wsgi","path":"%s"}\n' % path).encode('ascii')
    start_response(
        '200 OK',
        [
            ('Content-Type', 'application/json'),
            ('Content-Length', str(len(body))),
            ('Cache-Control', 'no-store'),
        ],
    )
    return [body]
