from rest_framework import serializers
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser

from .models import Testimonial
from .serializers import TestimonialListSerializer, TestimonialSerializer, apply_testimonial_filters


def _is_admin(user) -> bool:
    return getattr(user, "role", None) == AdminUser.ROLE_ADMIN


def _permission_denied_response():
    return Response(
        {"success": False, "error": {"code": 403, "message": "Insufficient permissions"}},
        status=status.HTTP_403_FORBIDDEN,
    )


class PublicTestimonialListAPIView(APIView):
    """
    GET /api/v1/website/testimonials/
    Public list: published testimonials (no JWT). Ordered by sort_order, id.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        qs = Testimonial.objects.filter(status=Testimonial.STATUS_PUBLISHED).order_by(
            "sort_order", "id"
        )
        ser = TestimonialListSerializer(qs, many=True, context={"request": request})
        return Response(
            {"success": True, "data": {"testimonials": ser.data}},
            status=status.HTTP_200_OK,
        )


class TestimonialListCreateAPIView(APIView):
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
        qs = Testimonial.objects.all().order_by("sort_order", "id")
        try:
            qs = apply_testimonial_filters(qs, request)
        except serializers.ValidationError:
            return Response(
                {"success": False, "error": {"code": 400, "message": "Invalid status filter"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        total = qs.count()
        published = qs.filter(status=Testimonial.STATUS_PUBLISHED).count()
        drafts = qs.filter(status=Testimonial.STATUS_DRAFT).count()

        page = self.paginate_queryset(qs)
        ser = TestimonialListSerializer(page if page is not None else qs, many=True, context={"request": request})
        payload = {
            "summary": {
                "total_testimonials": total,
                "published": published,
                "drafts": drafts,
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
        ser = TestimonialSerializer(data=request.data)
        if not ser.is_valid():
            message = self._first_error(ser)
            return Response(
                {"success": False, "error": {"code": 400, "message": message}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj = ser.save(created_by=request.user)
        return Response(
            {"success": True, "data": TestimonialSerializer(obj, context={"request": request}).data},
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _first_error(serializer):
        errors = serializer.errors
        if "non_field_errors" in errors and errors["non_field_errors"]:
            return str(errors["non_field_errors"][0])
        for field in ("name", "role", "review", "rating", "avatar", "status", "sort_order"):
            if field in errors and errors[field]:
                return str(errors[field][0])
        for val in errors.values():
            if isinstance(val, list) and val:
                return str(val[0])
        return "Invalid request"


class TestimonialDetailAPIView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return Testimonial.objects.filter(pk=pk).first()

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Testimonial not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"success": True, "data": TestimonialSerializer(obj, context={"request": request}).data})

    def patch(self, request, pk):
        if not _is_admin(request.user):
            return _permission_denied_response()
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Testimonial not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        ser = TestimonialSerializer(obj, data=request.data, partial=True)
        if not ser.is_valid():
            message = TestimonialListCreateAPIView._first_error(ser)
            return Response(
                {"success": False, "error": {"code": 400, "message": message}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj = ser.save()
        return Response({"success": True, "data": TestimonialSerializer(obj, context={"request": request}).data})

    def delete(self, request, pk):
        if not _is_admin(request.user):
            return _permission_denied_response()
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {"success": False, "error": {"code": 404, "message": "Testimonial not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        obj.delete()
        return Response({"success": True, "message": "Testimonial deleted successfully"}, status=status.HTTP_200_OK)
