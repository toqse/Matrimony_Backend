"""Serializers for Transaction APIs."""
from rest_framework import serializers
from .models import Transaction


class TransactionListSerializer(serializers.ModelSerializer):
    plan_name = serializers.SerializerMethodField()
    status = serializers.CharField(source='payment_status')
    type = serializers.CharField(source='transaction_type')
    date = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = ['plan_name', 'transaction_id', 'amount', 'type', 'status', 'date']

    def get_plan_name(self, obj):
        if obj.plan_id:
            return obj.plan.name
        return obj.get_transaction_type_display()

    def get_amount(self, obj):
        return float(obj.total_amount or obj.amount or 0)

    def get_date(self, obj):
        return obj.created_at.strftime('%Y-%m-%d') if obj.created_at else None


class TransactionDetailSerializer(serializers.ModelSerializer):
    plan_name = serializers.SerializerMethodField()
    status = serializers.CharField(source='payment_status')
    date = serializers.SerializerMethodField()
    payment_method = serializers.CharField()
    amount = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = ['transaction_id', 'plan_name', 'amount', 'status', 'payment_method', 'date']

    def get_plan_name(self, obj):
        if obj.plan_id:
            return obj.plan.name
        return obj.get_transaction_type_display()

    def get_amount(self, obj):
        return float(obj.total_amount or obj.amount or 0)

    def get_date(self, obj):
        return obj.created_at.strftime('%Y-%m-%d') if obj.created_at else None
