"""
JWT auth that refreshes last_seen (throttled) so online status works app-wide.
"""
from datetime import datetime

from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from core.last_seen import touch_user_last_seen


class JWTAuthenticationWithLastSeen(JWTAuthentication):
    """Same as SimpleJWT; updates User.last_seen on successful auth (throttled)."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return result
        user, validated_token = result
        # Reject tokens issued before user's invalidation timestamp (set on logout).
        invalid_before = getattr(user, "tokens_invalid_before", None)
        if invalid_before:
            iat = validated_token.get("iat")
            if iat:
                issued_at = datetime.fromtimestamp(int(iat), tz=timezone.utc)
                if issued_at < invalid_before:
                    raise AuthenticationFailed("Token is no longer valid. Please login again.")
        if user and getattr(user, 'is_authenticated', False):
            touch_user_last_seen(user.pk, min_interval_seconds=90)
        return result
