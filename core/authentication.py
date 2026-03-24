"""
JWT auth that refreshes last_seen (throttled) so online status works app-wide.
Supports both 'user_id' and legacy 'id' in token payload.
"""

from datetime import datetime

from django.utils import timezone
from django.contrib.auth import get_user_model

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from core.last_seen import touch_user_last_seen


User = get_user_model()


class JWTAuthenticationWithLastSeen(JWTAuthentication):
    """
    Custom JWT Authentication:
    - Supports both 'user_id' and 'id' in token
    - Handles token invalidation
    - Updates last_seen (throttled)
    """

    def authenticate(self, request):
        """
        Override authenticate to:
        - Validate token
        - Attach user
        - Update last_seen
        """
        result = super().authenticate(request)

        if result is None:
            return None

        user, validated_token = result

        # 🔒 Token invalidation check (logout support)
        invalid_before = getattr(user, "tokens_invalid_before", None)
        if invalid_before:
            iat = validated_token.get("iat")
            if iat:
                issued_at = datetime.fromtimestamp(int(iat), tz=timezone.utc)
                if issued_at < invalid_before:
                    raise AuthenticationFailed("Token is no longer valid. Please login again.")

        # 🟢 Update last_seen (throttled)
        if user and getattr(user, "is_authenticated", False):
            touch_user_last_seen(user.pk, min_interval_seconds=90)

        return (user, validated_token)

    def get_user(self, validated_token):
        """
        Override get_user to support:
        - 'user_id' (standard)
        - 'id' (legacy)
        """

        # ✅ Try both keys
        user_id = validated_token.get("user_id") or validated_token.get("id")

        if not user_id:
            raise AuthenticationFailed("Token contained no recognizable user identification")

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise AuthenticationFailed("User not found")

        return user