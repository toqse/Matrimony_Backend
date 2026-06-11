from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction as db_transaction
from django.http import HttpResponse
from django.urls import reverse
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from profiles.models import UserProfile

from plans.models import Transaction
from plans.services import (
    can_horoscope_match,
    consume_horoscope_match,
    get_user_plan_status,
    horoscope_quota_exhausted_response,
    plan_expired_response,
)

from .jathagam import generate_pdf
from .models import AstrologyPdfCredit
from .serializers import (
    AstrologyPdfOrderSerializer,
    AstrologyPdfVerifySerializer,
    HoroscopeProfilePublicSerializer,
    HoroscopeProfileSerializer,
    PoruthamCheckRequestSerializer,
)
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
from .services.public_url_signing import (
    sign_pdf_credit_access,
    verify_pdf_credit_access,
)


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


class HoroscopeProfileMeView(APIView):
    """GET /api/v1/astrology/horoscope/me/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import HoroscopeProfile

        try:
            hp = HoroscopeProfile.objects.get(user=request.user)
        except HoroscopeProfile.DoesNotExist:
            return Response(
                {'success': True, 'data': {'exists': False, 'is_calculated': False}}
            )
        return Response(
            {'success': True, 'data': HoroscopeProfileSerializer(hp).data}
        )


class HoroscopeProfileDetailView(APIView):
    """GET /api/v1/astrology/horoscope/<uuid:user_id>/"""

    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        from .models import HoroscopeProfile

        if get_user_plan_status(request.user) != 'active':
            return Response(
                plan_expired_response(request.user),
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            hp = HoroscopeProfile.objects.get(user_id=user_id)
        except HoroscopeProfile.DoesNotExist:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'Not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {'success': True, 'data': HoroscopeProfilePublicSerializer(hp).data}
        )


class UpdateBirthCoordinatesView(APIView):
    """PATCH /api/v1/astrology/birth-coordinates/"""

    permission_classes = [IsAuthenticated]

    def patch(self, request):
        try:
            lat = float(request.data.get('latitude'))
            lon = float(request.data.get('longitude'))
        except (TypeError, ValueError):
            return Response(
                {'success': False, 'error': {'code': 400, 'message': 'Invalid coordinates.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return Response(
                {
                    'success': False,
                    'error': {'code': 400, 'message': 'Coordinates out of range.'},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile, _ = UserProfile.objects.get_or_create(user=request.user, defaults={})
        profile.birth_latitude = lat
        profile.birth_longitude = lon
        profile.save(update_fields=['birth_latitude', 'birth_longitude', 'updated_at'])
        return Response({'success': True, 'data': {'latitude': lat, 'longitude': lon}})


class PoruthamCheckView(APIView):
    """POST /api/v1/astrology/porutham/"""

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

        from .models import HoroscopeProfile, PoruthamResult
        from .porutham import calculate_porutham

        try:
            bride_profile = UserProfile.objects.select_related('user').get(
                pk=serializer.validated_data['bride_id']
            )
            groom_profile = UserProfile.objects.select_related('user').get(
                pk=serializer.validated_data['groom_id']
            )
        except UserProfile.DoesNotExist:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'Profile not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            bride_hp = bride_profile.user.horoscope_profile
            groom_hp = groom_profile.user.horoscope_profile
        except HoroscopeProfile.DoesNotExist:
            return Response(
                {
                    'success': False,
                    'error': {
                        'code': 400,
                        'message': 'Horoscope not found for one or both profiles.',
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not bride_hp.is_exe_done() or not groom_hp.is_exe_done():
            return Response(
                {
                    'success': False,
                    'error': {
                        'code': 400,
                        'message': 'Horoscope not yet calculated. Windows EXE must run first.',
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = calculate_porutham(bride_hp, groom_hp)

        PoruthamResult.objects.update_or_create(
            bride=bride_profile.user,
            groom=groom_profile.user,
            defaults={
                'dinam': result['dinam'],
                'ganam': result['ganam'],
                'mahendra': result['mahendra'],
                'sthree_deerga': result['sthree_deerga'],
                'yoni': result['yoni'],
                'rasi': result['rasi'],
                'rasyadhipam': result['rasyadhipam'],
                'vasyam': result['vasyam'],
                'rajju_dosham': result['rajju_dosham'],
                'vedha_dosham': result['vedha_dosham'],
                'chovva_dosham': result['chovva_dosham'],
                'bride_papatha': result['bride_papatha'],
                'groom_papatha': result['groom_papatha'],
                'total_porutham_count': result['total_porutham_count'],
                'uthamam_count': result['uthamam_count'],
                'madhyamam_count': result['madhyamam_count'],
                'adhamam_count': result['adhamam_count'],
                'has_dosha': result['has_dosha'],
                'overall_result': result['overall_result'],
            },
        )

        consume_horoscope_match(request.user)
        return Response({'success': True, 'data': result}, status=status.HTTP_200_OK)


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
            out = create_order(
                user_matri_id=getattr(request.user, 'matri_id', '') or '', product=product
            )
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


class HoroscopeDecoderDebugView(APIView):
    """
    GET /api/horoscope/debug/<id>/

    Returns the raw EXE strings and Django's decoded house-by-house output for
    rasi / amsa / bhava. Read-only diagnostic endpoint for decoder verification.
    Open when settings.DEBUG is True; otherwise requires authentication.
    """

    def get_permissions(self):
        if settings.DEBUG:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        from .models import HoroscopeProfile
        from .services.horoscope_decoder import decode_amsa, decode_bhava, decode_rasi

        try:
            hp = HoroscopeProfile.objects.get(pk=pk)
        except HoroscopeProfile.DoesNotExist:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'Not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                'id': hp.pk,
                'raw_rasi': hp.pr_rasi or '',
                'decoded_rasi': decode_rasi(hp.pr_rasi),
                'raw_amsa': hp.pr_amsa or '',
                'decoded_amsa': decode_amsa(hp.pr_amsa),
                'raw_bhava': hp.pr_bhav or '',
                'decoded_bhava': decode_bhava(hp.pr_bhav),
                'pr_star': hp.pr_star,
                'pr_pada': hp.pr_pada,
                'pr_dasabalance': hp.pr_dasabalance,
            }
        )


class JathagamPDFView(APIView):
    """GET /api/v1/astrology/jathagam/<horoscope_id>/ — owner or staff only."""

    permission_classes = [IsAuthenticated]

    def get(self, request, horoscope_id):
        from .models import HoroscopeProfile

        try:
            hp = HoroscopeProfile.objects.select_related('user').get(id=horoscope_id)
        except HoroscopeProfile.DoesNotExist:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'Not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        user = request.user
        if not (hp.user_id == user.id or user.is_staff or user.is_superuser):
            return Response(
                {'success': False, 'error': {'code': 403, 'message': 'Not allowed.'}},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not hp.pr_rasi or len(hp.pr_rasi) < 11:
            return Response(
                {
                    'success': False,
                    'error': {'code': 400, 'message': 'Horoscope not calculated yet.'},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        content, fmt = generate_pdf(hp)
        name = f"jathagam_{hp.pr_name}_{hp.pr_dob}".replace(' ', '_')
        if fmt == 'pdf':
            resp = HttpResponse(content, content_type='application/pdf')
            resp['Content-Disposition'] = f'attachment; filename="{name}.pdf"'
            return resp
        return HttpResponse(content, content_type='text/html')


class AstrologyPdfJathakamDownloadView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                'success': False,
                'error': {
                    'code': 503,
                    'message': 'Jathakam PDF temporarily unavailable during system upgrade.',
                },
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class AstrologyPdfThalakuriDownloadView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                'success': False,
                'error': {
                    'code': 503,
                    'message': 'Thalakuri PDF temporarily unavailable during system upgrade.',
                },
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
