"""Local RazorpayOrder row is created when checkout creates a Razorpay order."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from plans.models import Plan, RazorpayOrder
from plans.services import RAZORPAY_PURPOSE_PLAN_PURCHASE


LOCMEM_CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'razorpay-order-persist-tests',
    }
}


@override_settings(
    CACHES=LOCMEM_CACHES,
    RAZORPAY_KEY_ID='rzp_test_key',
    RAZORPAY_KEY_SECRET='rzp_test_secret',
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_BROKER_URL='memory://',
    CELERY_RESULT_BACKEND=None,
)
class RazorpayOrderPersistTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            mobile='+919876543299',
            password='x',
            name='Order User',
            gender='M',
            role='user',
        )
        self.user.is_active = True
        self.user.save(update_fields=['is_active'])
        self.plan = Plan.objects.create(
            name='Gold',
            price=Decimal('499'),
            duration_days=30,
            profile_view_limit=10,
            interest_limit=5,
            chat_limit=5,
            contact_view_limit=5,
            horoscope_match_limit=0,
            is_active=True,
            is_published=True,
        )
        self.client.force_authenticate(user=self.user)

    def test_plan_order_creates_local_razorpay_order(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            'id': 'order_local_persist_1',
            'amount': 49900,
            'currency': 'INR',
            'receipt': 'pltestreceipt',
        }
        with patch('plans.razorpay_client.requests.post', return_value=mock_resp):
            res = self.client.post(
                '/api/v1/plans/order/',
                {'plan_id': self.plan.pk, 'payment_option': 'plan_only'},
                format='json',
            )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json().get('success'))
        row = RazorpayOrder.objects.get(razorpay_order_id='order_local_persist_1')
        self.assertEqual(row.status, RazorpayOrder.STATUS_CREATED)
        self.assertEqual(row.purpose, RAZORPAY_PURPOSE_PLAN_PURCHASE)
        self.assertEqual(row.user_id, self.user.pk)
        self.assertEqual(row.plan_id, self.plan.pk)
        self.assertEqual(row.amount_paise, 49900)
        self.assertEqual(row.currency, 'INR')
        self.assertFalse(row.razorpay_payment_id)
