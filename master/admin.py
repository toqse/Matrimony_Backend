from django.contrib import admin
from .models import (
    Country, State, District, City,
    Religion, Caste, MotherTongue, Height, MaritalStatus, IncomeRange,
    Education, EducationSubject, Occupation, Branch,
)


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active']
    list_filter = ['is_active']


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'country', 'is_active']
    list_filter = ['country', 'is_active']


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ['name', 'state', 'is_active']
    list_filter = ['state', 'is_active']


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ['name', 'district', 'is_active']
    list_filter = ['district', 'is_active']


@admin.register(Religion)
class ReligionAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    list_filter = ['is_active']


@admin.register(Caste)
class CasteAdmin(admin.ModelAdmin):
    list_display = ['name', 'religion', 'is_active']
    list_filter = ['religion', 'is_active']


@admin.register(MotherTongue)
class MotherTongueAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    list_filter = ['is_active']


@admin.register(Height)
class HeightAdmin(admin.ModelAdmin):
    list_display = ['value_cm', 'display_label', 'is_active']


@admin.register(MaritalStatus)
class MaritalStatusAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']


@admin.register(IncomeRange)
class IncomeRangeAdmin(admin.ModelAdmin):
    list_display = ['name', 'min_value', 'max_value', 'is_active']


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']


@admin.register(EducationSubject)
class EducationSubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']


@admin.register(Occupation)
class OccupationAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active']
