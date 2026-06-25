from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.permissions import IsAdminUser

from .models import MobileAppConfig
from .serializers import MobileAppConfigSerializer


def _config_response(config, status_code=status.HTTP_200_OK):
    return Response(
        {
            "success": True,
            "data": MobileAppConfigSerializer(config).data,
        },
        status=status_code,
    )


class PublicAppConfigAPIView(APIView):
    """GET /api/v1/website/app-config/ — public mobile version check (no token)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return _config_response(MobileAppConfig.load())


class AdminAppConfigAPIView(APIView):
    """GET/PATCH /api/v1/admin/app-config/ — super-admin mobile app config."""

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        return _config_response(MobileAppConfig.load())

    def patch(self, request):
        config = MobileAppConfig.load()
        serializer = MobileAppConfigSerializer(config, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": 400,
                        "message": "Validation failed.",
                        "details": serializer.errors,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer.save()
        return _config_response(config)
