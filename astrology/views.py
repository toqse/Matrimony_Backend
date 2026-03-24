from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from profiles.models import UserProfile

from .models import Horoscope
from .serializers import (
    HoroscopeGenerateRequestSerializer,
    HoroscopeSerializer,
    PoruthamCheckRequestSerializer,
    PoruthamResultSerializer,
)
from .services.chart_service import generate_chart_image
from .services.horoscope_service import generate_horoscope_payload
from .services.porutham_service import calculate_porutham
from .services.utils import build_birth_input_hash


def _profile_birth_inputs(profile: UserProfile):
    dob = getattr(profile.user, 'dob', None)
    tob = getattr(profile, 'time_of_birth', None)
    pob = getattr(profile, 'place_of_birth', '')
    if not dob or not tob or not pob:
        return None
    return dob, tob, pob


def _create_or_update_horoscope(profile: UserProfile):
    birth_inputs = _profile_birth_inputs(profile)
    if not birth_inputs:
        raise ValueError('Profile birth details are incomplete.')

    dob, tob, pob = birth_inputs
    payload = generate_horoscope_payload(dob, tob, pob)
    horoscope, _ = Horoscope.objects.update_or_create(
        profile=profile,
        defaults=payload,
    )
    return horoscope


class GenerateHoroscopeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = HoroscopeGenerateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = get_object_or_404(UserProfile.objects.select_related('user'), pk=serializer.validated_data['profile_id'])
        try:
            horoscope = _create_or_update_horoscope(profile)
        except ValueError as exc:
            return Response(
                {'success': False, 'error': {'code': 400, 'message': str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({'success': True, 'data': HoroscopeSerializer(horoscope).data}, status=status.HTTP_200_OK)


class HoroscopeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, profile_id):
        profile = get_object_or_404(UserProfile.objects.select_related('user'), pk=profile_id)
        horoscope = Horoscope.objects.filter(profile=profile).first()

        birth_inputs = _profile_birth_inputs(profile)
        if horoscope is None:
            if not birth_inputs:
                return Response(
                    {'success': False, 'error': {'code': 400, 'message': 'Birth details not available.'}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            horoscope = _create_or_update_horoscope(profile)
        elif birth_inputs:
            dob, tob, pob = birth_inputs
            current_hash = build_birth_input_hash(dob, tob, pob)
            if horoscope.birth_input_hash != current_hash:
                horoscope = _create_or_update_horoscope(profile)

        return Response({'success': True, 'data': HoroscopeSerializer(horoscope).data}, status=status.HTTP_200_OK)


class PoruthamCheckView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PoruthamCheckRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bride = Horoscope.objects.filter(profile_id=serializer.validated_data['bride_id']).first()
        groom = Horoscope.objects.filter(profile_id=serializer.validated_data['groom_id']).first()
        if not bride or not groom:
            return Response(
                {'success': False, 'error': {'code': 400, 'message': 'Bride or groom horoscope not found.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = calculate_porutham(bride, groom)
        return Response(
            {'success': True, 'data': PoruthamResultSerializer(result).data},
            status=status.HTTP_200_OK,
        )


class HoroscopeChartView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, profile_id):
        style = request.query_params.get('style', 'south')
        profile = get_object_or_404(UserProfile, pk=profile_id)
        horoscope = Horoscope.objects.filter(profile=profile).first()
        if not horoscope:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'Horoscope not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        cache_key = f'astrology_chart:{profile_id}:{style}:{horoscope.updated_at.isoformat()}'
        png_bytes = cache.get(cache_key)
        if png_bytes is None:
            png_bytes = generate_chart_image(horoscope.grahanila, style=style)
            cache.set(cache_key, png_bytes, timeout=60 * 60)
        return HttpResponse(png_bytes, content_type='image/png')
