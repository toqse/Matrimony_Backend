"""Filters for master CRUD APIs."""
from django_filters import rest_framework as filters
from .models import Caste


class CasteFilter(filters.FilterSet):
    religion_id = filters.NumberFilter(field_name='religion_id')

    class Meta:
        model = Caste
        fields = ['religion_id']
