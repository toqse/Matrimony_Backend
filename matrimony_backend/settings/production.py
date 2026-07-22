"""
Production settings.
"""
from .base import *

DEBUG = False
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True
# Allow LB/Docker probes without HTTPS redirect
SECURE_REDIRECT_EXEMPT = [r'^health/$']

# Set via env in production, e.g. https://admin.example.com,https://www.example.com
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# Quieter startup in production
LOG_DATABASE_CONFIG = env.bool('LOG_DATABASE_CONFIG', default=False)
