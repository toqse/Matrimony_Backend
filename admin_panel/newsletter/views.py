from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.pagination import StandardPagination
from admin_panel.permissions import IsAdminUser

from .models import NewsletterSubscriber
from .serializers import NewsletterSubscriberSerializer


def _normalize_email(raw: str) -> str:
    return (raw or "").strip().lower()


class NewsletterSubscribeAPIView(APIView):
    """POST /api/v1/website/newsletter/subscribe/ — public footer signup."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        email = _normalize_email(request.data.get("email"))
        if not email:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Email is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            validate_email(email)
        except ValidationError:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Enter a valid email address."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        source = (request.data.get("source") or "footer").strip()[:50] or "footer"
        existing = NewsletterSubscriber.objects.filter(email=email).first()
        if existing:
            if existing.is_active:
                return Response(
                    {
                        "success": True,
                        "data": {"message": "You're already subscribed."},
                    },
                    status=status.HTTP_200_OK,
                )
            existing.is_active = True
            existing.source = source
            existing.save(update_fields=["is_active", "source", "updated_at"])
            return Response(
                {
                    "success": True,
                    "data": {"message": "Subscribed successfully."},
                },
                status=status.HTTP_200_OK,
            )

        NewsletterSubscriber.objects.create(email=email, source=source)
        return Response(
            {
                "success": True,
                "data": {"message": "Subscribed successfully."},
            },
            status=status.HTTP_201_CREATED,
        )


class NewsletterSubscriberListAPIView(APIView):
    """GET /api/v1/admin/newsletter/ — list footer newsletter signups (admin only)."""

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        qs = NewsletterSubscriber.objects.all().order_by("-subscribed_at")

        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(email__icontains=search)

        active = (request.query_params.get("is_active") or "").strip().lower()
        if active in ("true", "1", "yes"):
            qs = qs.filter(is_active=True)
        elif active in ("false", "0", "no"):
            qs = qs.filter(is_active=False)

        total = NewsletterSubscriber.objects.count()
        active_count = NewsletterSubscriber.objects.filter(is_active=True).count()

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = NewsletterSubscriberSerializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        response.data["summary"] = {
            "total": total,
            "active": active_count,
            "inactive": total - active_count,
        }
        return Response({"success": True, "data": response.data}, status=status.HTTP_200_OK)
