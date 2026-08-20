from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import User
from astrology.models import AstrologyPdfCredit, HoroscopeProfile
from astrology.services.public_url_signing import sign_pdf_credit_access
from astrology.views import (
    AstrologyPdfOrderView,
    AstrologyPdfThalakuriDownloadView,
    get_purchased_pdf_credit,
)
from plans.models import Transaction

LOCMEM_CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'astrology-pdf-order-tests',
    }
}


def _rasi_string(moon_sign: int = 2) -> str:
    chars = []
    for i in range(11):
        if i == 2:
            chars.append(chr(ord('A') + moon_sign - 1))
        else:
            chars.append('A')
    return ''.join(chars)


class AstrologyPdfOrderAlreadyPurchasedTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            mobile='+919876543600',
            password='x',
            name='Pdf Buyer',
        )
        HoroscopeProfile.objects.update_or_create(
            user=self.user,
            defaults={
                'pr_rasi': _rasi_string(),
                'pr_star': 5,
                'pr_pada': 1,
                'pr_name': 'Pdf Buyer',
                'pr_dob': '2000-01-01',
            },
        )
        self.factory = APIRequestFactory()

    def _thalakuri_credit(self):
        txn = Transaction.objects.create(
            user=self.user,
            plan=None,
            amount=Decimal('20'),
            service_charge=Decimal('0'),
            total_amount=Decimal('20'),
            payment_method=Transaction.PAYMENT_RAZORPAY,
            payment_status=Transaction.STATUS_SUCCESS,
            transaction_type=Transaction.TYPE_THALAKURI_PDF,
            transaction_id=f'pay_test_{self.user.pk}',
        )
        return AstrologyPdfCredit.objects.create(
            user=self.user,
            product=AstrologyPdfCredit.PRODUCT_THALAKURI,
            transaction=txn,
        )

    def test_get_purchased_pdf_credit_returns_latest_success_credit(self):
        credit = self._thalakuri_credit()
        found = get_purchased_pdf_credit(self.user, AstrologyPdfCredit.PRODUCT_THALAKURI)
        self.assertIsNotNone(found)
        self.assertEqual(found.pk, credit.pk)

    def test_get_purchased_pdf_credit_ignores_failed_transaction(self):
        txn = Transaction.objects.create(
            user=self.user,
            plan=None,
            amount=Decimal('20'),
            service_charge=Decimal('0'),
            total_amount=Decimal('20'),
            payment_method=Transaction.PAYMENT_RAZORPAY,
            payment_status=Transaction.STATUS_FAILED,
            transaction_type=Transaction.TYPE_THALAKURI_PDF,
            transaction_id='pay_failed',
        )
        AstrologyPdfCredit.objects.create(
            user=self.user,
            product=AstrologyPdfCredit.PRODUCT_THALAKURI,
            transaction=txn,
        )
        self.assertIsNone(
            get_purchased_pdf_credit(self.user, AstrologyPdfCredit.PRODUCT_THALAKURI)
        )

    @override_settings(CACHES=LOCMEM_CACHES)
    @patch('astrology.views.create_order')
    def test_order_returns_already_purchased_when_credit_exists(self, mock_create_order):
        credit = self._thalakuri_credit()
        request = self.factory.post(
            '/api/v1/astrology/pdf/order/',
            {'product': 'thalakuri'},
            format='json',
        )
        force_authenticate(request, user=self.user)
        response = AstrologyPdfOrderView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        data = response.data['data']
        self.assertTrue(data['already_purchased'])
        self.assertEqual(data['credit_id'], credit.pk)
        self.assertIn('download_url', data)
        self.assertNotIn('order_id', data)
        mock_create_order.assert_not_called()

class AstrologyPdfThalakuriCreditDownloadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            mobile='+919876543602',
            password='x',
            name='Download User',
        )
        HoroscopeProfile.objects.update_or_create(
            user=self.user,
            defaults={
                'pr_rasi': _rasi_string(),
                'pr_star': 8,
                'pr_pada': 2,
                'pr_name': 'Download User',
                'pr_dob': '1995-05-05',
            },
        )
        txn = Transaction.objects.create(
            user=self.user,
            plan=None,
            amount=Decimal('20'),
            service_charge=Decimal('0'),
            total_amount=Decimal('20'),
            payment_method=Transaction.PAYMENT_RAZORPAY,
            payment_status=Transaction.STATUS_SUCCESS,
            transaction_type=Transaction.TYPE_THALAKURI_PDF,
            transaction_id='pay_dl_test',
        )
        self.credit = AstrologyPdfCredit.objects.create(
            user=self.user,
            product=AstrologyPdfCredit.PRODUCT_THALAKURI,
            transaction=txn,
        )
        self.factory = APIRequestFactory()

    @override_settings(CACHES=LOCMEM_CACHES)
    @patch('astrology.views._thalakuri_pdf_http_response')
    def test_credit_signed_download_returns_pdf(self, mock_pdf):
        from django.http import HttpResponse

        mock_pdf.return_value = HttpResponse(b'%PDF-1.4', content_type='application/pdf')
        sig = sign_pdf_credit_access(self.credit.pk)
        request = self.factory.get(
            '/api/v1/astrology/pdf/thalakuri/',
            {'sig': sig, 'credit_id': str(self.credit.pk)},
        )
        response = AstrologyPdfThalakuriDownloadView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        mock_pdf.assert_called_once()

    @override_settings(CACHES=LOCMEM_CACHES)
    def test_invalid_credit_signature_rejected(self):
        request = self.factory.get(
            '/api/v1/astrology/pdf/thalakuri/',
            {'sig': 'bad-sig', 'credit_id': str(self.credit.pk)},
        )
        response = AstrologyPdfThalakuriDownloadView.as_view()(request)
        self.assertEqual(response.status_code, 403)


class AstrologyPdfOrderHoroscopeGateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            mobile='+919876543603',
            password='x',
            name='Not Ready User',
        )
        HoroscopeProfile.objects.update_or_create(
            user=self.user,
            defaults={
                'pr_rasi': '',
                'pr_star': None,
                'pr_name': 'Not Ready User',
                'pr_dob': '2000-01-01',
            },
        )
        self.factory = APIRequestFactory()

    @override_settings(CACHES=LOCMEM_CACHES)
    @patch('astrology.views.create_order')
    def test_order_rejected_when_horoscope_not_generated(self, mock_create_order):
        request = self.factory.post(
            '/api/v1/astrology/pdf/order/',
            {'product': 'thalakuri'},
            format='json',
        )
        force_authenticate(request, user=self.user)
        response = AstrologyPdfOrderView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data['is_horoscope_generated'])
        mock_create_order.assert_not_called()

    @override_settings(CACHES=LOCMEM_CACHES)
    @patch('astrology.views.create_order')
    def test_order_allows_already_purchased_when_horoscope_not_ready(self, mock_create_order):
        txn = Transaction.objects.create(
            user=self.user,
            plan=None,
            amount=Decimal('20'),
            service_charge=Decimal('0'),
            total_amount=Decimal('20'),
            payment_method=Transaction.PAYMENT_RAZORPAY,
            payment_status=Transaction.STATUS_SUCCESS,
            transaction_type=Transaction.TYPE_THALAKURI_PDF,
            transaction_id='pay_gate_test',
        )
        credit = AstrologyPdfCredit.objects.create(
            user=self.user,
            product=AstrologyPdfCredit.PRODUCT_THALAKURI,
            transaction=txn,
        )
        request = self.factory.post(
            '/api/v1/astrology/pdf/order/',
            {'product': 'thalakuri'},
            format='json',
        )
        force_authenticate(request, user=self.user)
        response = AstrologyPdfOrderView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['data']['already_purchased'])
        self.assertEqual(response.data['data']['credit_id'], credit.pk)
        mock_create_order.assert_not_called()
