"""
Transaction APIs for the Transactions page.

GET /api/v1/transactions/summary/
GET /api/v1/transactions/
GET /api/v1/transactions/count/
GET /api/v1/transactions/{transaction_id}/
"""
from django.db.models import Sum
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import Transaction, UserPlan
from .serializers_transactions import TransactionListSerializer, TransactionDetailSerializer


class TransactionSummaryView(APIView):
    """
    GET /api/v1/transactions/summary/
    Returns total spent, active plan name, and next renewal date.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # total_spent: sum of successful plan_purchase transactions
        total_spent = Transaction.objects.filter(
            user=user,
            payment_status=Transaction.STATUS_SUCCESS,
            transaction_type=Transaction.TYPE_PLAN_PURCHASE,
        ).aggregate(total=Sum('total_amount'))['total'] or 0

        # active plan & next renewal from UserPlan
        active_plan_name = None
        next_renewal = None
        try:
            user_plan = UserPlan.objects.select_related('plan').get(user=user, is_active=True)
            active_plan_name = user_plan.plan.name
            next_renewal = user_plan.valid_until.strftime('%Y-%m-%d') if user_plan.valid_until else None
        except UserPlan.DoesNotExist:
            pass

        return Response({
            'success': True,
            'data': {
                'total_spent': float(total_spent),
                'active_plan': active_plan_name,
                'next_renewal': next_renewal,
            }
        })


class TransactionListView(APIView):
    """
    GET /api/v1/transactions/?page=1&limit=10
    Returns paginated list of all transactions for the logged-in user,
    ordered by created_at descending.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page = 1
        try:
            limit = max(1, min(100, int(request.query_params.get('limit', 10))))
        except (ValueError, TypeError):
            limit = 10

        qs = Transaction.objects.filter(user=request.user).select_related('plan').order_by('-created_at')
        total = qs.count()
        offset = (page - 1) * limit
        transactions = qs[offset: offset + limit]

        serializer = TransactionListSerializer(transactions, many=True)
        return Response({
            'success': True,
            'data': {
                'total': total,
                'page': page,
                'limit': limit,
                'transactions': serializer.data,
            }
        })


class TransactionCountView(APIView):
    """
    GET /api/v1/transactions/count/
    Returns total number of transactions for the logged-in user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        total = Transaction.objects.filter(user=request.user).count()
        return Response({
            'success': True,
            'data': {
                'total_transactions': total,
            }
        })


class TransactionDetailView(APIView):
    """
    GET /api/v1/transactions/{transaction_id}/
    Returns full details of a single transaction belonging to the logged-in user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, transaction_id):
        try:
            txn = Transaction.objects.select_related('plan').get(
                transaction_id=transaction_id,
                user=request.user,
            )
        except Transaction.DoesNotExist:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'Transaction not found'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = TransactionDetailSerializer(txn)
        return Response({'success': True, 'data': serializer.data})
