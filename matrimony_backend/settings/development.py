"""
Development settings.
"""
from .base import *

DEBUG = True
CORS_ALLOW_ALL_ORIGINS = True

# Faster OTP rate limit window for local testing (~10 seconds instead of 10 minutes)
OTP_RATE_LIMIT_WINDOW_MINUTES = 1 / 6

# Admin login OTP: avoid 429 during local / QA testing
ADMIN_OTP_REQUEST_LIMIT = 50
ADMIN_OTP_REQUEST_WINDOW_SECONDS = 60
ADMIN_OTP_FAILED_ATTEMPT_LIMIT = 10
ADMIN_OTP_LOCK_SECONDS = 60

# Relax DRF throttling in development to avoid "Too Many Requests" during local testing
REST_FRAMEWORK = {**REST_FRAMEWORK, 'DEFAULT_THROTTLE_RATES': {
    'anon': '10000/hour',
    'user': '10000/hour',
}}
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])