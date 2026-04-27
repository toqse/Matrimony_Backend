from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser

from .models import SuccessStory
from .serializers import SuccessStoryListSerializer, SuccessStorySerializer, apply_success_story_filters


def _is_admin(user) -> bool:
    return getattr(user, "role", None) == AdminUser.ROLE_ADMIN


def _permission_denied_response():
    return Response(
        {"success": False, "error": {"code": 403, "message": "Insufficient permissions"}},
        status=status.HTTP_403_FORBIDDEN,
    )


class PublicSuccessStoryListAPIView(APIView):
    """
    GET /api/v1/website/success-stories/
    Public list: published stories created by an admin (no JWT). Paginated (same defaults as DRF, page size 20).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            from rest_framework.settings import api_settings

            pagination_class = api_settings.DEFAULT_PAGINATION_CLASS
            self._paginator = pagination_class() if pagination_class else None
        return self._paginator

    def paginate_queryset(self, queryset):
        if self.paginator is None:
            return None
        return self.paginator.paginate_queryset(queryset, self.request, view=self)

    def get_paginated_response(self, data):
        return self.paginator.get_paginated_response(data)

    def get(self, request):
        qs = (
            SuccessStory.objects.filter(
                status=SuccessStory.STATUS_PUBLISHED,
                created_by__isnull=False,
                created_by__role=AdminUser.ROLE_ADMIN,
            )
            .select_related("created_by")
            .order_by("-is_featured", "-created_at", "-id")
        )
        page = self.paginate_queryset(qs)
        ser = SuccessStoryListSerializer(
            page if page is not None else qs, many=True, context={"request": request}
        )
        if page is not None:
            paged = self.get_paginated_response(ser.data)
            d = paged.data
            return Response(
                {
                    "success": True,
                    "data": {
                        "count": d["count"],
                        "next": d.get("next"),
                        "previous": d.get("previous"),
                        "stories": d["results"],
                    },
                },
                status=status.HTTP_200_OK,
            )
        return Response({"success": True, "data": {"stories": ser.data}}, status=status.HTTP_200_OK)


class SuccessStoryListCreateAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            from rest_framework.settings import api_settings

            pagination_class = api_settings.DEFAULT_PAGINATION_CLASS
            self._paginator = pagination_class() if pagination_class else None
        return self._paginator

    def paginate_queryset(self, queryset):
        if self.paginator is None:
            return None
        return self.paginator.paginate_queryset(queryset, self.request, view=self)

    def get_paginated_response(self, data):
        return self.paginator.get_paginated_response(data)

    def get(self, request):
        qs = SuccessStory.objects.all().order_by("-created_at")
        try:
            qs = apply_success_story_filters(qs, request)
        except serializers.ValidationError:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Invalid status filter"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        total_stories = qs.count()
        published = qs.filter(status=SuccessStory.STATUS_PUBLISHED).count()
        drafts = qs.filter(status=SuccessStory.STATUS_DRAFT).count()
        total_views = qs.aggregate(v=Sum("views_count")).get("v") or 0

        page = self.paginate_queryset(qs)
        ser = SuccessStoryListSerializer(page if page is not None else qs, many=True, context={"request": request})
        payload = {
            "summary": {
                "total_stories": total_stories,
                "published": published,
                "drafts": drafts,
                "total_views": int(total_views),
            },
            "results": ser.data,
        }
        if page is not None:
            paged = self.get_paginated_response(payload["results"]).data
            paged["summary"] = payload["summary"]
            return Response({"success": True, "data": paged})
        return Response({"success": True, "data": payload})

    def post(self, request):
        if not _is_admin(request.user):
            return _permission_denied_response()
        ser = SuccessStorySerializer(data=request.data)
        if not ser.is_valid():
            message = self._first_error(ser)
            return Response(
                {"success": False, "error": {"code": 400, "message": message}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            obj = ser.save(created_by=request.user)
            if obj.is_featured:
                SuccessStory.objects.filter(is_featured=True).exclude(pk=obj.pk).update(is_featured=False)
        return Response(
            {"success": True, "data": SuccessStorySerializer(obj, context={"request": request}).data},
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _first_error(serializer):
        errors = serializer.errors
        if "non_field_errors" in errors and errors["non_field_errors"]:
            return str(errors["non_field_errors"][0])
        for key in ("couple_name_1", "couple_name_2"):
            if key in errors:
                return "Both partner names are required"
        for field in ("wedding_date", "location", "story_text", "couple_photo", "status"):
            if field in errors and errors[field]:
                return str(errors[field][0])
        for val in errors.values():
            if isinstance(val, list) and val:
                return str(val[0])
        return "Invalid request"


class SuccessStoryDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return SuccessStory.objects.filter(pk=pk).first()

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Story not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"success": True, "data": SuccessStorySerializer(obj, context={"request": request}).data})

    def patch(self, request, pk):
        if not _is_admin(request.user):
            return _permission_denied_response()
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Story not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        ser = SuccessStorySerializer(obj, data=request.data, partial=True)
        if not ser.is_valid():
            message = SuccessStoryListCreateAPIView._first_error(ser)
            return Response(
                {"success": False, "error": {"code": 400, "message": message}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            obj = ser.save()
            if obj.is_featured:
                SuccessStory.objects.filter(is_featured=True).exclude(pk=obj.pk).update(is_featured=False)
        return Response({"success": True, "data": SuccessStorySerializer(obj, context={"request": request}).data})

    def delete(self, request, pk):
        if not _is_admin(request.user):
            return _permission_denied_response()
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Story not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        obj.delete()
        return Response({"success": True, "message": "Story deleted successfully"}, status=status.HTTP_200_OK)


class PublishSuccessStoryAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not _is_admin(request.user):
            return _permission_denied_response()
        obj = SuccessStory.objects.filter(pk=pk).first()
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Story not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if obj.status == SuccessStory.STATUS_PUBLISHED:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Story is already published"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj.status = SuccessStory.STATUS_PUBLISHED
        obj.save(update_fields=["status", "updated_at"])
        return Response({"success": True, "data": SuccessStorySerializer(obj, context={"request": request}).data})


class ToggleFeaturedSuccessStoryAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not _is_admin(request.user):
            return _permission_denied_response()
        obj = SuccessStory.objects.filter(pk=pk).first()
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Story not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        with transaction.atomic():
            target = not obj.is_featured
            if target:
                SuccessStory.objects.filter(is_featured=True).exclude(pk=obj.pk).update(is_featured=False)
            obj.is_featured = target
            obj.save(update_fields=["is_featured", "updated_at"])
        return Response({"success": True, "data": SuccessStorySerializer(obj, context={"request": request}).data})
