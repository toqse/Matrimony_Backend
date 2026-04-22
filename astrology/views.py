from decimal import Decimal
from urllib.parse import urlencode

from django.core.cache import cache
from django.db import transaction as db_transaction
from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from profiles.models import UserProfile

from plans.models import Transaction
from plans.services import (
    can_horoscope_match,
    consume_horoscope_match,
    get_user_plan_status,
    horoscope_quota_exhausted_response,
    plan_expired_response,
)

from .models import AstrologyPdfCredit, Horoscope
from .serializers import (
    AstrologyPdfOrderSerializer,
    AstrologyPdfVerifySerializer,
    BirthDetailCandidateSerializer,
    HoroscopeGenerateRequestSerializer,
    HoroscopeSerializer,
    PoruthamCheckRequestSerializer,
    PoruthamResultSerializer,
)
from .services.chart_service import generate_chart_image
from .services.generate_ui_service import build_match_ui, build_person_card, resolve_bride_groom_horoscopes
from .services.match_ui_copy import generate_ui_config
from .services.horoscope_runtime import (
    create_or_update_horoscope,
    resolve_horoscope_for_profile,
)
from .services.jathakam_pdf_service import build_jathakam_pdf
from .services.match_report_service import build_match_report_pdf
from .services.razorpay_pdf_orders import (
    RazorpayApiError,
    RazorpayNotConfiguredError,
    amount_paise,
    catalog_price_inr,
    create_order,
    fetch_payment,
    transaction_type_for_product,
    verify_payment_signature,
)
from .services.thalakuri_pdf_service import build_thalakuri_pdf
from .services.porutham_service import calculate_porutham
from .services.public_url_signing import (
    sign_chart_access,
    sign_match_report_access,
    sign_pdf_credit_access,
    verify_chart_access,
    verify_match_report_access,
    verify_pdf_credit_access,
)
def _chart_absolute_url(request, profile_id: int, style: str = 'south') -> str:
    rel = reverse('astrology:horoscope_chart', kwargs={'profile_id': profile_id})
    query = urlencode({
        'sig': sign_chart_access(profile_id),
        'style': style,
    })
    return request.build_absolute_uri(f'{rel}?{query}')


def _match_report_absolute_url(request, bride_matri_id: str, groom_matri_id: str) -> str:
    rel = reverse('astrology:match_report')
    query = urlencode({
        'bride_matri_id': bride_matri_id,
        'groom_matri_id': groom_matri_id,
        'sig': sign_match_report_access(bride_matri_id, groom_matri_id),
    })
    return request.build_absolute_uri(f'{rel}?{query}')


def _pdf_public_download_url(request, credit: AstrologyPdfCredit) -> str:
    sig = sign_pdf_credit_access(credit.pk)
    if credit.product == AstrologyPdfCredit.PRODUCT_JATHAKAM:
        rel = reverse('astrology:astrology_pdf_jathakam')
    else:
        rel = reverse('astrology:astrology_pdf_thalakuri')
    query = urlencode({'sig': sig, 'credit_id': credit.pk})
    return request.build_absolute_uri(f'{rel}?{query}')


def _astrology_pdf_verify_success_data(
    request, credit: AstrologyPdfCredit, *, already_verified: bool
) -> dict:
    return {
        'credited': True,
        'already_verified': already_verified,
        'product': credit.product,
        'credit_id': credit.pk,
        'download_url': _pdf_public_download_url(request, credit),
    }


def _chart_request_allowed(request, profile_id: int) -> bool:
    sig = request.query_params.get('sig', '')
    if verify_chart_access(sig, profile_id):
        return True
    user = getattr(request, 'user', None)
    return bool(user and user.is_authenticated)


def _match_report_request_allowed(request, bride_mid: str, groom_mid: str) -> bool:
    sig = request.query_params.get('sig', '')
    if verify_match_report_access(sig, bride_mid, groom_mid):
        return True
    user = getattr(request, 'user', None)
    return bool(user and user.is_authenticated)


def _horoscope_summary(horoscope: Horoscope) -> dict:
    return {
        'rasi': horoscope.rasi,
        'nakshatra': horoscope.nakshatra,
        'nakshatra_pada': horoscope.nakshatra_pada,
        'gana': horoscope.gana,
    }


def _current_user_profile_pk(user) -> int | None:
    return UserProfile.objects.filter(user=user).values_list('pk', flat=True).first()


def _generate_is_self_only(request, matri_id: str, partner_mid: str) -> bool:
    owner = (getattr(request.user, 'matri_id', None) or '').strip()
    p = (partner_mid or '').strip()
    return (matri_id == owner) and not (p and p != matri_id)


class GenerateHoroscopeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = HoroscopeGenerateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        matri_id = serializer.validated_data['matri_id'].strip()
        partner_mid_raw = (serializer.validated_data.get('partner_matri_id') or '').strip()
        if not _generate_is_self_only(request, matri_id, partner_mid_raw):
            if get_user_plan_status(request.user) != 'active':
                return Response(
                    plan_expired_response(request.user),
                    status=status.HTTP_403_FORBIDDEN,
                )

        user = get_object_or_404(User.objects.filter(is_active=True), matri_id=matri_id)
        UserProfile.objects.get_or_create(user=user, defaults={})
        profile = UserProfile.objects.select_related('user').get(user=user)
        try:
            horoscope = create_or_update_horoscope(profile)
        except ValueError as exc:
            return Response(
                {'success': False, 'error': {'code': 400, 'message': str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        horoscope = Horoscope.objects.select_related('profile__user').get(pk=horoscope.pk)

        data = dict(HoroscopeSerializer(horoscope).data)
        data['chart_url'] = _chart_absolute_url(request, profile.pk)
        data['partner_chart_url'] = None
        data['match_report_pdf_url'] = None
        data['primary'] = build_person_card(profile, horoscope, data['chart_url'])
        data['partner'] = None
        data['match'] = None
        data['ui_config'] = generate_ui_config()
        data['title'] = 'Horoscope'
        data['subtitle'] = None

        partner_mid = partner_mid_raw
        if partner_mid and partner_mid != matri_id:
            try:
                partner_user = User.objects.get(matri_id=partner_mid, is_active=True)
            except User.DoesNotExist:
                partner_user = None
            if partner_user:
                UserProfile.objects.get_or_create(user=partner_user, defaults={})
                partner_profile = UserProfile.objects.select_related('user').get(user=partner_user)
                try:
                    create_or_update_horoscope(partner_profile)
                except ValueError:
                    pass
                partner_h = (
                    Horoscope.objects.filter(profile=partner_profile)
                    .select_related('profile__user')
                    .first()
                )
                if partner_h:
                    allowed, _rem = can_horoscope_match(request.user)
                    if not allowed:
                        return Response(
                            horoscope_quota_exhausted_response(),
                            status=status.HTTP_403_FORBIDDEN,
                        )
                    data['partner_chart_url'] = _chart_absolute_url(request, partner_profile.pk)
                    bride_h, groom_h = resolve_bride_groom_horoscopes(
                        profile, partner_profile, horoscope, partner_h
                    )
                    bride_mid = getattr(bride_h.profile.user, 'matri_id', '') or ''
                    groom_mid = getattr(groom_h.profile.user, 'matri_id', '') or ''
                    data['match_report_pdf_url'] = _match_report_absolute_url(
                        request, bride_mid, groom_mid
                    )
                    data['partner'] = build_person_card(
                        partner_profile, partner_h, data['partner_chart_url']
                    )
                    data['match'] = build_match_ui(
                        profile, partner_profile, horoscope, partner_h
                    )
                    data['title'] = 'Marriage Compatibility Report'
                    data['subtitle'] = (
                        f"{data['match']['bride_matri_id']} vs {data['match']['groom_matri_id']}"
                    )
                    consume_horoscope_match(request.user)

        return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)


class BirthDetailCandidatesListView(APIView):
    """
    GET /api/v1/astrology/birth-detail-candidates/
    Lists other active members with complete birth inputs (DOB + time_of_birth + place_of_birth),
    same rule as horoscope generation. Excludes sensitive fields.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if get_user_plan_status(request.user) != 'active':
            return Response(
                plan_expired_response(request.user),
                status=status.HTTP_403_FORBIDDEN,
            )
        horoscope_exists = Horoscope.objects.filter(profile_id=OuterRef('pk'))
        qs = (
            UserProfile.objects.select_related('user')
            .annotate(stored_horoscope_exists=Exists(horoscope_exists))
            .filter(
                user__is_active=True,
                user__dob__isnull=False,
                time_of_birth__isnull=False,
            )
            .exclude(user=request.user)
            .exclude(place_of_birth='')
        )

        all_genders = (request.query_params.get('all_genders') or '').strip().lower() in (
            '1',
            'true',
            'yes',
        )
        if not all_genders:
            gender = getattr(request.user, 'gender', None)
            if gender == 'M':
                qs = qs.filter(user__gender='F')
            elif gender == 'F':
                qs = qs.filter(user__gender='M')

        search = (request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(user__matri_id__icontains=search) | Q(user__name__icontains=search)
            )

        qs = qs.order_by('-user__created_at')

        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            limit = max(1, min(50, int(request.query_params.get('limit', 10))))
        except (TypeError, ValueError):
            limit = 10

        total = qs.count()
        start = (page - 1) * limit
        page_qs = qs[start : start + limit]
        ser = BirthDetailCandidateSerializer(page_qs, many=True)
        return Response(
            {
                'success': True,
                'data': {
                    'total': total,
                    'page': page,
                    'limit': limit,
                    'results': ser.data,
                },
            },
            status=status.HTTP_200_OK,
        )


class HoroscopeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, profile_id):
        profile = get_object_or_404(UserProfile.objects.select_related('user'), pk=profile_id)
        if profile.user_id != request.user.id and get_user_plan_status(request.user) != 'active':
            return Response(
                plan_expired_response(request.user),
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            horoscope = resolve_horoscope_for_profile(profile)
        except ValueError as exc:
            return Response(
                {'success': False, 'error': {'code': 400, 'message': str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({'success': True, 'data': HoroscopeSerializer(horoscope).data}, status=status.HTTP_200_OK)


class HoroscopeMeView(APIView):
    """
    GET /api/v1/astrology/horoscope/me/
    Current user's full horoscope (including grahanila) plus signed chart_url.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        UserProfile.objects.get_or_create(user=request.user, defaults={})
        profile = UserProfile.objects.select_related('user').get(user=request.user)
        try:
            horoscope = resolve_horoscope_for_profile(profile)
        except ValueError as exc:
            return Response(
                {'success': False, 'error': {'code': 400, 'message': str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = dict(HoroscopeSerializer(horoscope).data)
        style = request.query_params.get('style', 'south')
        data['chart_url'] = _chart_absolute_url(request, profile.pk, style=style)
        return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)


class PoruthamCheckView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if get_user_plan_status(request.user) != 'active':
            return Response(
                plan_expired_response(request.user),
                status=status.HTTP_403_FORBIDDEN,
            )
        allowed, _rem = can_horoscope_match(request.user)
        if not allowed:
            return Response(
                horoscope_quota_exhausted_response(),
                status=status.HTTP_403_FORBIDDEN,
            )
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
        consume_horoscope_match(request.user)
        return Response(
            {'success': True, 'data': PoruthamResultSerializer(result).data},
            status=status.HTTP_200_OK,
        )


class HoroscopeChartView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, profile_id):
        if not _chart_request_allowed(request, profile_id):
            return Response(
                {
                    'success': False,
                    'error': {
                        'code': 401,
                        'message': 'Authentication credentials were not provided or signature is invalid/expired.',
                    },
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        sig = request.query_params.get('sig', '')
        if not verify_chart_access(sig, profile_id) and request.user.is_authenticated:
            my_pk = _current_user_profile_pk(request.user)
            if my_pk != profile_id and get_user_plan_status(request.user) != 'active':
                return Response(
                    plan_expired_response(request.user),
                    status=status.HTTP_403_FORBIDDEN,
                )
        style = request.query_params.get('style', 'south')
        profile = get_object_or_404(UserProfile, pk=profile_id)
        horoscope = (
            Horoscope.objects.filter(profile=profile)
            .select_related('profile__user')
            .first()
        )
        if not horoscope:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'Horoscope not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        cache_key = f'astrology_chart:{profile_id}:{style}:{horoscope.updated_at.isoformat()}'
        png_bytes = cache.get(cache_key)
        if png_bytes is None:
            png_bytes = generate_chart_image(
                horoscope.grahanila,
                style=style,
                nakshatra_en=horoscope.nakshatra,
                gender_code=getattr(horoscope.profile.user, 'gender', None),
            )
            cache.set(cache_key, png_bytes, timeout=60 * 60)
        return HttpResponse(png_bytes, content_type='image/png')


class MatchReportPdfView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        bride_mid = request.query_params.get('bride_matri_id', '').strip()
        groom_mid = request.query_params.get('groom_matri_id', '').strip()
        if not bride_mid or not groom_mid:
            return Response(
                {
                    'success': False,
                    'error': {
                        'code': 400,
                        'message': 'Query params bride_matri_id and groom_matri_id are required.',
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not _match_report_request_allowed(request, bride_mid, groom_mid):
            return Response(
                {
                    'success': False,
                    'error': {
                        'code': 401,
                        'message': 'Authentication credentials were not provided or signature is invalid/expired.',
                    },
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        sig = request.query_params.get('sig', '')
        if not verify_match_report_access(sig, bride_mid, groom_mid):
            if request.user.is_authenticated:
                if get_user_plan_status(request.user) != 'active':
                    return Response(
                        plan_expired_response(request.user),
                        status=status.HTTP_403_FORBIDDEN,
                    )

        try:
            bride_user = User.objects.get(matri_id=bride_mid, is_active=True)
            groom_user = User.objects.get(matri_id=groom_mid, is_active=True)
        except User.DoesNotExist:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'User not found for matri_id.'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        bride_profile = UserProfile.objects.filter(user=bride_user).first()
        groom_profile = UserProfile.objects.filter(user=groom_user).first()
        if not bride_profile or not groom_profile:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'Profile not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        bride_h = Horoscope.objects.filter(profile=bride_profile).first()
        groom_h = Horoscope.objects.filter(profile=groom_profile).first()
        if not bride_h or not groom_h:
            return Response(
                {
                    'success': False,
                    'error': {'code': 400, 'message': 'Horoscope missing for bride or groom.'},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        porutham_result = calculate_porutham(bride_h, groom_h)
        pdf_bytes = build_match_report_pdf(
            bride_mid,
            groom_mid,
            _horoscope_summary(bride_h),
            _horoscope_summary(groom_h),
            porutham_result,
        )
        filename = f'MatchReport_{bride_mid}_{groom_mid}.pdf'.replace(' ', '')
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response


class AstrologyPdfOrderView(APIView):
    """POST: create Razorpay order for Jathakam or Thalakuri PDF."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = AstrologyPdfOrderSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {
                    'success': False,
                    'error': {'code': 400, 'message': 'Validation failed.', 'details': ser.errors},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        product = ser.validated_data['product']
        try:
            out = create_order(user_matri_id=getattr(request.user, 'matri_id', '') or '', product=product)
        except RazorpayNotConfiguredError as exc:
            return Response(
                {
                    'success': False,
                    'error': {'code': 503, 'message': str(exc)},
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except RazorpayApiError as exc:
            return Response(
                {
                    'success': False,
                    'error': {'code': 502, 'message': str(exc)},
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        price = catalog_price_inr(product)
        return Response(
            {
                'success': True,
                'data': {
                    'product': product,
                    'price_inr': float(price),
                    'order_id': out['order_id'],
                    'amount': out['amount'],
                    'currency': out['currency'],
                    'key_id': out['key_id'],
                },
            },
            status=status.HTTP_200_OK,
        )


class AstrologyPdfVerifyView(APIView):
    """POST: verify Razorpay payment and grant one PDF download credit."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = AstrologyPdfVerifySerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {
                    'success': False,
                    'error': {'code': 400, 'message': 'Validation failed.', 'details': ser.errors},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        product = ser.validated_data['product']
        order_id = ser.validated_data['razorpay_order_id'].strip()
        payment_id = ser.validated_data['razorpay_payment_id'].strip()
        signature = ser.validated_data['razorpay_signature'].strip()

        try:
            sig_ok = verify_payment_signature(order_id, payment_id, signature)
        except RazorpayNotConfiguredError as exc:
            return Response(
                {'success': False, 'error': {'code': 503, 'message': str(exc)}},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if not sig_ok:
            return Response(
                {
                    'success': False,
                    'error': {'code': 400, 'message': 'Invalid payment signature.'},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        expected_type = transaction_type_for_product(product)
        expected_paise = amount_paise(product)

        def _idempotent_response_for_txn(txn_row: Transaction):
            if txn_row.user_id != request.user.id:
                return Response(
                    {
                        'success': False,
                        'error': {'code': 403, 'message': 'Payment belongs to another account.'},
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            if txn_row.payment_status != Transaction.STATUS_SUCCESS:
                return Response(
                    {
                        'success': False,
                        'error': {'code': 400, 'message': 'Payment transaction is not successful.'},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if txn_row.transaction_type != expected_type:
                return Response(
                    {
                        'success': False,
                        'error': {'code': 400, 'message': 'Payment does not match this product.'},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            with db_transaction.atomic():
                credit, _ = AstrologyPdfCredit.objects.get_or_create(
                    transaction=txn_row,
                    defaults={
                        'user': request.user,
                        'product': product,
                    },
                )
            if credit.product != product:
                return Response(
                    {
                        'success': False,
                        'error': {'code': 400, 'message': 'Credit product mismatch.'},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {
                    'success': True,
                    'data': _astrology_pdf_verify_success_data(
                        request, credit, already_verified=True
                    ),
                },
                status=status.HTTP_200_OK,
            )

        existing_early = Transaction.objects.filter(transaction_id=payment_id).first()
        if existing_early:
            return _idempotent_response_for_txn(existing_early)

        try:
            pay = fetch_payment(payment_id)
        except RazorpayNotConfiguredError as exc:
            return Response(
                {'success': False, 'error': {'code': 503, 'message': str(exc)}},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except RazorpayApiError as exc:
            return Response(
                {'success': False, 'error': {'code': 502, 'message': str(exc)}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if pay.get('order_id') != order_id:
            return Response(
                {
                    'success': False,
                    'error': {'code': 400, 'message': 'Order id does not match payment.'},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if pay.get('status') != 'captured':
            return Response(
                {
                    'success': False,
                    'error': {'code': 400, 'message': 'Payment is not captured.'},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if int(pay.get('amount', 0)) != expected_paise:
            return Response(
                {
                    'success': False,
                    'error': {'code': 400, 'message': 'Payment amount does not match product price.'},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        price = catalog_price_inr(product)

        with db_transaction.atomic():
            existing_locked = (
                Transaction.objects.select_for_update()
                .filter(transaction_id=payment_id)
                .first()
            )
            if existing_locked:
                txn_row = existing_locked
            else:
                txn_row = Transaction.objects.create(
                    user=request.user,
                    plan=None,
                    amount=price,
                    service_charge=Decimal('0'),
                    total_amount=price,
                    payment_method=Transaction.PAYMENT_RAZORPAY,
                    payment_status=Transaction.STATUS_SUCCESS,
                    transaction_type=expected_type,
                    transaction_id=payment_id,
                )
                credit = AstrologyPdfCredit.objects.create(
                    user=request.user,
                    product=product,
                    transaction=txn_row,
                )
                return Response(
                    {
                        'success': True,
                        'data': _astrology_pdf_verify_success_data(
                            request, credit, already_verified=False
                        ),
                    },
                    status=status.HTTP_200_OK,
                )

            if txn_row.user_id != request.user.id:
                return Response(
                    {
                        'success': False,
                        'error': {'code': 403, 'message': 'Payment belongs to another account.'},
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            if txn_row.payment_status != Transaction.STATUS_SUCCESS:
                return Response(
                    {
                        'success': False,
                        'error': {'code': 400, 'message': 'Payment transaction is not successful.'},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if txn_row.transaction_type != expected_type:
                return Response(
                    {
                        'success': False,
                        'error': {'code': 400, 'message': 'Payment does not match this product.'},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            credit, _ = AstrologyPdfCredit.objects.get_or_create(
                transaction=txn_row,
                defaults={
                    'user': request.user,
                    'product': product,
                },
            )
            if credit.product != product:
                return Response(
                    {
                        'success': False,
                        'error': {'code': 400, 'message': 'Credit product mismatch.'},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(
            {
                'success': True,
                'data': _astrology_pdf_verify_success_data(
                    request, credit, already_verified=True
                ),
            },
            status=status.HTTP_200_OK,
        )


def _serve_pdf_by_signed_credit(request, credit_id: int, expected_product: str, builder):
    """
    Public download: valid sig + credit_id. Consumes that credit and returns PDF bytes.
    """
    with db_transaction.atomic():
        try:
            credit = AstrologyPdfCredit.objects.select_for_update().get(pk=credit_id)
        except AstrologyPdfCredit.DoesNotExist:
            return None, Response(
                {
                    'success': False,
                    'error': {'code': 404, 'message': 'PDF credit not found.'},
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        if credit.product != expected_product:
            return None, Response(
                {
                    'success': False,
                    'error': {'code': 400, 'message': 'URL does not match this PDF type.'},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if credit.consumed_at is not None:
            return None, Response(
                {
                    'success': False,
                    'error': {'code': 410, 'message': 'This download link has already been used.'},
                },
                status=status.HTTP_410_GONE,
            )
        user = credit.user
        profile = UserProfile.objects.select_related('user').get(user=user)
        try:
            horoscope = resolve_horoscope_for_profile(profile)
        except ValueError as exc:
            return None, Response(
                {'success': False, 'error': {'code': 400, 'message': str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        pdf_bytes = builder(horoscope, user, profile)
        credit.consumed_at = timezone.now()
        credit.save(update_fields=['consumed_at', 'updated_at'])
    mid = (user.matri_id or 'profile').replace(' ', '')
    label = 'Jathakam' if expected_product == AstrologyPdfCredit.PRODUCT_JATHAKAM else 'Thalakuri'
    filename = f'{label}_{mid}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response, None


def _consume_credit_and_build_pdf(request, product: str, builder):
    UserProfile.objects.get_or_create(user=request.user, defaults={})
    profile = UserProfile.objects.select_related('user').get(user=request.user)
    user = request.user
    with db_transaction.atomic():
        credit = (
            AstrologyPdfCredit.objects.select_for_update()
            .filter(user=user, product=product, consumed_at__isnull=True)
            .order_by('created_at')
            .first()
        )
        if not credit:
            return None, Response(
                {
                    'success': False,
                    'error': {
                        'code': 403,
                        'message': 'No unused purchase for this product. Pay and verify first.',
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            horoscope = resolve_horoscope_for_profile(profile)
        except ValueError as exc:
            return None, Response(
                {'success': False, 'error': {'code': 400, 'message': str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        pdf_bytes = builder(horoscope, user, profile)
        credit.consumed_at = timezone.now()
        credit.save(update_fields=['consumed_at', 'updated_at'])
    mid = (user.matri_id or 'profile').replace(' ', '')
    label = 'Jathakam' if product == AstrologyPdfCredit.PRODUCT_JATHAKAM else 'Thalakuri'
    filename = f'{label}_{mid}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response, None


class AstrologyPdfJathakamDownloadView(APIView):
    """
    GET with JWT: consume first unused jathakam credit (same user).
    GET with sig + credit_id (from verify response): public browser download, no Authorization header.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        sig = (request.query_params.get('sig') or '').strip()
        raw_cid = request.query_params.get('credit_id')
        if sig and raw_cid is not None:
            try:
                cid = int(raw_cid)
            except (TypeError, ValueError):
                return Response(
                    {
                        'success': False,
                        'error': {'code': 400, 'message': 'Invalid credit_id.'},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not verify_pdf_credit_access(sig, cid):
                return Response(
                    {
                        'success': False,
                        'error': {
                            'code': 401,
                            'message': 'Invalid or expired signature for PDF download.',
                        },
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            resp, err = _serve_pdf_by_signed_credit(
                request, cid, AstrologyPdfCredit.PRODUCT_JATHAKAM, build_jathakam_pdf
            )
            if err:
                return err
            return resp
        if not request.user.is_authenticated:
            return Response(
                {
                    'success': False,
                    'error': {
                        'code': 401,
                        'message': 'Use Authorization: Bearer or open the signed download_url from verify.',
                    },
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        resp, err = _consume_credit_and_build_pdf(
            request, AstrologyPdfCredit.PRODUCT_JATHAKAM, build_jathakam_pdf
        )
        if err:
            return err
        return resp


class AstrologyPdfThalakuriDownloadView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        sig = (request.query_params.get('sig') or '').strip()
        raw_cid = request.query_params.get('credit_id')
        if sig and raw_cid is not None:
            try:
                cid = int(raw_cid)
            except (TypeError, ValueError):
                return Response(
                    {
                        'success': False,
                        'error': {'code': 400, 'message': 'Invalid credit_id.'},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not verify_pdf_credit_access(sig, cid):
                return Response(
                    {
                        'success': False,
                        'error': {
                            'code': 401,
                            'message': 'Invalid or expired signature for PDF download.',
                        },
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            resp, err = _serve_pdf_by_signed_credit(
                request, cid, AstrologyPdfCredit.PRODUCT_THALAKURI, build_thalakuri_pdf
            )
            if err:
                return err
            return resp
        if not request.user.is_authenticated:
            return Response(
                {
                    'success': False,
                    'error': {
                        'code': 401,
                        'message': 'Use Authorization: Bearer or open the signed download_url from verify.',
                    },
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        resp, err = _consume_credit_and_build_pdf(
            request, AstrologyPdfCredit.PRODUCT_THALAKURI, build_thalakuri_pdf
        )
        if err:
            return err
        return resp
