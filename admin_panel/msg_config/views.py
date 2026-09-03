from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.permissions import IsAdminUser

from .models import MsgConfig
from .serializers import MsgConfigSerializer


def _config_response(config, status_code=status.HTTP_200_OK):
    return Response(
        {
            "success": True,
            "data": MsgConfigSerializer(config).data,
        },
        status=status_code,
    )


class AdminMsgConfigAPIView(APIView):
    """GET/PATCH /api/v1/admin/msg-config/ — MSG91 WhatsApp / OTP settings."""

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        return _config_response(MsgConfig.load())

    def patch(self, request):
        config = MsgConfig.load()
        serializer = MsgConfigSerializer(config, data=request.data, partial=True)
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
