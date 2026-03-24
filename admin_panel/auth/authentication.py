from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from .models import AdminUser


class AdminJWTAuthentication(JWTAuthentication):
    """
    JWT auth for admin panel endpoints.
    Expects `admin_user_id` claim in the access token.
    """

    def get_user(self, validated_token):
        admin_user_id = validated_token.get("admin_user_id")
        if not admin_user_id:
            raise InvalidToken("Invalid token payload.")
        try:
            user = AdminUser.objects.select_related("branch").get(pk=admin_user_id)
        except AdminUser.DoesNotExist:
            raise InvalidToken("User not found.")
        if not user.is_active:
            raise InvalidToken("User is inactive.")
        return user

