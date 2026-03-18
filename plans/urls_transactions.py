"""URL patterns for Transaction APIs."""
from django.urls import path
from .views_transactions import (
    TransactionSummaryView,
    TransactionListView,
    TransactionCountView,
    TransactionDetailView,
)

urlpatterns = [
    path('', TransactionListView.as_view()),
    path('summary/', TransactionSummaryView.as_view()),
    path('count/', TransactionCountView.as_view()),
    path('<str:transaction_id>/', TransactionDetailView.as_view()),
]
