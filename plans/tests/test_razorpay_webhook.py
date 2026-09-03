"""Tests for Razorpay webhook signature + fulfillment."""
from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from astrology.models import AstrologyPdfCredit
from plans.models import Plan, Transaction, UserPlan
from plans.razorpay_client import RazorpayNotConfiguredError, inr_to_paise
from plans.services import RAZORPAY_PURPOSE_PLAN_PURCHASE, compute_plan_purchase_amounts

LOCMEM_CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'razorpay-webhook-tests',
    }
}

WEBHOOK_SECRET = 'whsec_test_secret_123'
WEBHOOK_URL = '/api/v1/payments/razorpay/webhook/'

TEST_SETTINGS = dict(
    CACHES=LOCMEM_CACHES,
    RAZORPAY_KEY_ID='rzp_test_key',
    RAZORPAY_KEY_SECRET='rzp_test_secret',
    RAZORPAY_WEBHOOK_SECRET=WEBHOOK_SECRET,
    ASTROLOGY_THALAKURI_PRICE_INR=Decimal('20'),
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    CELERY_BROKER_URL='memory://',
    CELERY_RESULT_BACKEND=None,
)


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()


def _payment_captured_payload(*, payment_id: str, order_id: str, amount: int) -> dict:
    return {
        'event': 'payment.captured',
        'payload': {
            'payment': {
                'entity': {
                    'id': payment_id,
                    'order_id': order_id,
                    'status': 'captured',
                    'amount': amount,
                }
            }
        },
    }


@override_settings(**TEST_SETTINGS)
class RazorpayWebhookTests(TestCase):
    def setUp(self):
        self._wa_patcher = patch(
            'notifications.whatsapp_notify.enqueue_subscription_confirmation',
            return_value=None,
        )
        self._wa_patcher.start()
        self.addCleanup(self._wa_patcher.stop)
        self.client = APIClient()
        self.user = User.objects.create_user(
            mobile='+919876543210',
            password='x',
            name='Webhook User',
            gender='M',
            role='user',
        )
        self.user.is_active = True
        self.user.save(update_fields=['is_active'])
        self.plan = Plan.objects.create(
            name='Premium',
            price=Decimal('999'),
            duration_days=90,
            profile_view_limit=20,
            interest_limit=10,
            chat_limit=10,
            contact_view_limit=10,
            horoscope_match_limit=5,
            is_active=True,
        )

    def _post_webhook(self, payload: dict, *, signature: str | None = None, secret: str = WEBHOOK_SECRET):
        body = json.dumps(payload).encode('utf-8')
        sig = signature if signature is not None else _sign(body, secret)
        return self.client.generic(
            'POST',
            WEBHOOK_URL,
            data=body,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=sig,
        )

    def test_invalid_webhook_signature_returns_400(self):
        payload = _payment_captured_payload(
            payment_id='pay_bad', order_id='order_bad', amount=100
        )
        res = self._post_webhook(payload, signature='deadbeef')
        self.assertEqual(res.status_code, 400, res.content)
        self.assertFalse(res.json().get('success'))

    def test_unknown_purpose_ignored_200(self):
        payment_id = 'pay_unknown'
        order_id = 'order_unknown'
        amount = 10000
        payload = _payment_captured_payload(
            payment_id=payment_id, order_id=order_id, amount=amount
        )
        with (
            patch('plans.views_razorpay_webhook.fetch_payment') as fp,
            patch('plans.views_razorpay_webhook.fetch_order') as fo,
        ):
            fp.return_value = {
                'id': payment_id,
                'order_id': order_id,
                'status': 'captured',
                'amount': amount,
            }
            fo.return_value = {
                'id': order_id,
                'amount': amount,
                'notes': {'purpose': 'something_else'},
            }
            res = self._post_webhook(payload)
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertTrue(data.get('success'))
        self.assertTrue(data.get('ignored'))
        self.assertEqual(Transaction.objects.filter(transaction_id=payment_id).count(), 0)

    def test_plan_purchase_fulfilled_once_idempotent(self):
        payment_id = 'pay_plan_1'
        order_id = 'order_plan_1'
        amount_inr, _, _, _ = compute_plan_purchase_amounts(
            self.user, self.plan, 'plan_only'
        )
        amount = inr_to_paise(amount_inr)
        payload = _payment_captured_payload(
            payment_id=payment_id, order_id=order_id, amount=amount
        )
        order = {
            'id': order_id,
            'amount': amount,
            'notes': {
                'purpose': RAZORPAY_PURPOSE_PLAN_PURCHASE,
                'user_id': str(self.user.pk),
                'matri_id': self.user.matri_id or '',
                'plan_id': str(self.plan.pk),
                'payment_option': 'plan_only',
            },
        }
        payment = {
            'id': payment_id,
            'order_id': order_id,
            'status': 'captured',
            'amount': amount,
        }

        with (
            patch('plans.views_razorpay_webhook.fetch_payment', return_value=payment),
            patch('plans.views_razorpay_webhook.fetch_order', return_value=order),
        ):
            res1 = self._post_webhook(payload)
            res2 = self._post_webhook(payload)

        self.assertEqual(res1.status_code, 200, res1.content)
        self.assertTrue(res1.json().get('fulfilled'))
        self.assertTrue(res1.json().get('created'))
        self.assertEqual(res2.status_code, 200, res2.content)
        self.assertTrue(res2.json().get('fulfilled'))
        self.assertFalse(res2.json().get('created'))

        self.assertEqual(
            Transaction.objects.filter(
                transaction_id=payment_id,
                payment_status=Transaction.STATUS_SUCCESS,
                transaction_type=Transaction.TYPE_PLAN_PURCHASE,
            ).count(),
            1,
        )
        up = UserPlan.objects.get(user=self.user)
        self.assertEqual(up.plan_id, self.plan.pk)
        self.assertTrue(up.is_active)

    def test_thalakuri_pdf_credit_once(self):
        payment_id = 'pay_thal_1'
        order_id = 'order_thal_1'
        amount = inr_to_paise(Decimal('20'))
        payload = _payment_captured_payload(
            payment_id=payment_id, order_id=order_id, amount=amount
        )
        order = {
            'id': order_id,
            'amount': amount,
            'notes': {
                'purpose': 'astrology_pdf',
                'product': AstrologyPdfCredit.PRODUCT_THALAKURI,
                'user_id': str(self.user.pk),
                'matri_id': self.user.matri_id or '',
            },
        }
        payment = {
            'id': payment_id,
            'order_id': order_id,
            'status': 'captured',
            'amount': amount,
        }

        with (
            patch('plans.views_razorpay_webhook.fetch_payment', return_value=payment),
            patch('plans.views_razorpay_webhook.fetch_order', return_value=order),
        ):
            res1 = self._post_webhook(payload)
            res2 = self._post_webhook(payload)

        self.assertEqual(res1.status_code, 200, res1.content)
        self.assertTrue(res1.json().get('created'))
        self.assertEqual(res2.status_code, 200, res2.content)
        self.assertFalse(res2.json().get('created'))

        self.assertEqual(
            AstrologyPdfCredit.objects.filter(
                user=self.user,
                product=AstrologyPdfCredit.PRODUCT_THALAKURI,
            ).count(),
            1,
        )
        self.assertEqual(
            Transaction.objects.filter(transaction_id=payment_id).count(),
            1,
        )

    def test_client_verify_after_webhook_is_idempotent(self):
        payment_id = 'pay_plan_verify'
        order_id = 'order_plan_verify'
        amount_inr, _, _, _ = compute_plan_purchase_amounts(
            self.user, self.plan, 'plan_only'
        )
        amount = inr_to_paise(amount_inr)
        order = {
            'id': order_id,
            'amount': amount,
            'notes': {
                'purpose': RAZORPAY_PURPOSE_PLAN_PURCHASE,
                'user_id': str(self.user.pk),
                'matri_id': self.user.matri_id or '',
                'plan_id': str(self.plan.pk),
                'payment_option': 'plan_only',
            },
        }
        payment = {
            'id': payment_id,
            'order_id': order_id,
            'status': 'captured',
            'amount': amount,
        }
        payload = _payment_captured_payload(
            payment_id=payment_id, order_id=order_id, amount=amount
        )

        with (
            patch('plans.views_razorpay_webhook.fetch_payment', return_value=payment),
            patch('plans.views_razorpay_webhook.fetch_order', return_value=order),
        ):
            wh = self._post_webhook(payload)
        self.assertEqual(wh.status_code, 200, wh.content)

        self.client.force_authenticate(user=self.user)
        with (
            patch('plans.views_payments.verify_payment_signature', return_value=True),
            patch('plans.views_payments.fetch_payment', return_value=payment),
            patch('plans.views_payments.fetch_order', return_value=order),
        ):
            res = self.client.post(
                '/api/v1/plans/verify/',
                {
                    'plan_id': self.plan.pk,
                    'payment_option': 'plan_only',
                    'razorpay_order_id': order_id,
                    'razorpay_payment_id': payment_id,
                    'razorpay_signature': 'sig',
                },
                format='json',
            )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json().get('success'))
        self.assertEqual(
            Transaction.objects.filter(transaction_id=payment_id).count(),
            1,
        )


@override_settings(
    CACHES=LOCMEM_CACHES,
    RAZORPAY_WEBHOOK_SECRET='',
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_BROKER_URL='memory://',
    CELERY_RESULT_BACKEND=None,
)
class RazorpayWebhookSecretMissingTests(TestCase):
    def test_missing_secret_returns_503(self):
        client = APIClient()
        body = b'{"event":"payment.captured"}'
        with patch(
            'plans.views_razorpay_webhook.verify_webhook_signature',
            side_effect=RazorpayNotConfiguredError(
                'Razorpay webhook secret is not configured.'
            ),
        ):
            res = client.generic(
                'POST',
                WEBHOOK_URL,
                data=body,
                content_type='application/json',
                HTTP_X_RAZORPAY_SIGNATURE='anything',
            )
        self.assertEqual(res.status_code, 503, res.content)
