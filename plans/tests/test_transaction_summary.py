from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from plans.models import Transaction
from plans.views_transactions import build_transaction_summary


class TransactionSummaryTotalSpentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            mobile="+919876543210",
            password="x",
            name="Spender",
        )

    def _txn(self, amount, txn_type, status=Transaction.STATUS_SUCCESS, suffix=""):
        return Transaction.objects.create(
            user=self.user,
            plan=None,
            amount=Decimal(str(amount)),
            service_charge=Decimal("0"),
            total_amount=Decimal(str(amount)),
            payment_method=Transaction.PAYMENT_RAZORPAY,
            payment_status=status,
            transaction_type=txn_type,
            transaction_id=f"pay_{txn_type}_{amount}{suffix}",
        )

    def test_total_spent_includes_thalakuri_and_jathakam_pdfs(self):
        self._txn(1000, Transaction.TYPE_PLAN_PURCHASE, suffix="_a")
        self._txn(999, Transaction.TYPE_PLAN_PURCHASE, suffix="_b")
        self._txn(14501, Transaction.TYPE_PLAN_PURCHASE, suffix="_c")
        self._txn(20, Transaction.TYPE_THALAKURI_PDF)
        self._txn(499, Transaction.TYPE_PLAN_PURCHASE, suffix="_d")
        self._txn(20, Transaction.TYPE_JATHAKAM_PDF)
        self._txn(50, Transaction.TYPE_THALAKURI_PDF, status=Transaction.STATUS_FAILED, suffix="_fail")
        self._txn(100, Transaction.TYPE_REFUND, suffix="_ref")

        summary = build_transaction_summary(self.user)
        # 1000+999+14501+20+499+20 = 17039; failed and refund excluded
        self.assertEqual(summary["total_spent"], 17039.0)
