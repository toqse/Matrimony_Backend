"""
Development settings.
"""
from .base import *

DEBUG = True
CORS_ALLOW_ALL_ORIGINS = True

# Faster OTP rate limit window for local testing (~10 seconds instead of 10 minutes)
OTP_RATE_LIMIT_WINDOW_MINUTES = 1 / 6

# Relax DRF throttling in development to avoid "Too Many Requests" during local testing
REST_FRAMEWORK = {**REST_FRAMEWORK, 'DEFAULT_THROTTLE_RATES': {
    'anon': '10000/hour',
    'user': '10000/hour',
}}
