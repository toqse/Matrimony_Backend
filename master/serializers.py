"""
Master dropdown serializers (minimal for list + search).
CRUD serializers for Religion, Caste, MotherTongue include id, name, is_active.
"""
from rest_framework import serializers
from .models import (
    Country, State, District, City,
    Religion, Caste, MotherTongue, Height, MaritalStatus, IncomeRange,
    Education, EducationSubject, Occupation,
)


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ['id', 'name', 'code']


class StateSerializer(serializers.ModelSerializer):
    class Meta:
        model = State
        fields = ['id', 'name', 'code', 'country']


class DistrictSerializer(serializers.ModelSerializer):
    class Meta:
        model = District
        fields = ['id', 'name', 'state']


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ['id', 'name', 'district']


class ReligionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Religion
        fields = ['id', 'name', 'is_active']


class CasteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Caste
        fields = ['id', 'name', 'is_active', 'religion']


class MotherTongueSerializer(serializers.ModelSerializer):
    class Meta:
        model = MotherTongue
        fields = ['id', 'name', 'is_active']


class HeightSerializer(serializers.ModelSerializer):
    class Meta:
        model = Height
        fields = ['id', 'value_cm', 'display_label']


class MaritalStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaritalStatus
        fields = ['id', 'name']


class IncomeRangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncomeRange
        fields = ['id', 'name', 'min_value', 'max_value']


class EducationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Education
        fields = ['id', 'name']


class EducationSubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = EducationSubject
        fields = ['id', 'name']


class OccupationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Occupation
        fields = ['id', 'name']
