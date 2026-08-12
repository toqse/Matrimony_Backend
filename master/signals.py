"""Invalidate Redis master-list caches when master rows change."""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from master import cache_utils as mc
from master.models import (
    Caste,
    City,
    Complexion,
    Country,
    District,
    Education,
    EducationSubject,
    EmploymentStatus,
    Height,
    IncomeRange,
    MaritalStatus,
    MotherTongue,
    Occupation,
    Religion,
    State,
)


def _invalidate(*resources):
    mc.invalidate_master_resources(*resources)


@receiver([post_save, post_delete], sender=Country)
def _country_changed(sender, **kwargs):
    _invalidate(mc.RESOURCE_COUNTRIES, mc.RESOURCE_STATES)


@receiver([post_save, post_delete], sender=State)
def _state_changed(sender, **kwargs):
    _invalidate(mc.RESOURCE_STATES, mc.RESOURCE_DISTRICTS)


@receiver([post_save, post_delete], sender=District)
def _district_changed(sender, **kwargs):
    _invalidate(mc.RESOURCE_DISTRICTS, mc.RESOURCE_CITIES)


@receiver([post_save, post_delete], sender=City)
def _city_changed(sender, **kwargs):
    _invalidate(mc.RESOURCE_CITIES)


@receiver([post_save, post_delete], sender=Religion)
def _religion_changed(sender, **kwargs):
    _invalidate(mc.RESOURCE_RELIGIONS, mc.RESOURCE_CASTES, mc.RESOURCE_MATCH_FILTERS)


@receiver([post_save, post_delete], sender=Caste)
def _caste_changed(sender, **kwargs):
    _invalidate(mc.RESOURCE_CASTES, mc.RESOURCE_MATCH_FILTERS)


@receiver([post_save, post_delete], sender=MotherTongue)
def _mother_tongue_changed(sender, **kwargs):
    _invalidate(mc.RESOURCE_MOTHER_TONGUES)


@receiver([post_save, post_delete], sender=Height)
def _height_changed(sender, **kwargs):
    _invalidate(mc.RESOURCE_HEIGHTS, mc.RESOURCE_MATCH_FILTERS)


@receiver([post_save, post_delete], sender=MaritalStatus)
def _marital_changed(sender, **kwargs):
    _invalidate(mc.RESOURCE_MARITAL_STATUSES, mc.RESOURCE_MATCH_FILTERS)


@receiver([post_save, post_delete], sender=Complexion)
def _complexion_changed(sender, **kwargs):
    _invalidate(mc.RESOURCE_COMPLEXIONS)


@receiver([post_save, post_delete], sender=IncomeRange)
def _income_changed(sender, **kwargs):
    _invalidate(mc.RESOURCE_INCOME_RANGES)


@receiver([post_save, post_delete], sender=Education)
def _education_changed(sender, **kwargs):
    _invalidate(mc.RESOURCE_EDUCATIONS, mc.RESOURCE_EDUCATION_SUBJECTS, mc.RESOURCE_MATCH_FILTERS)


@receiver([post_save, post_delete], sender=EducationSubject)
def _education_subject_changed(sender, **kwargs):
    _invalidate(mc.RESOURCE_EDUCATION_SUBJECTS)


@receiver([post_save, post_delete], sender=Occupation)
def _occupation_changed(sender, **kwargs):
    _invalidate(mc.RESOURCE_OCCUPATIONS, mc.RESOURCE_MATCH_FILTERS)


@receiver([post_save, post_delete], sender=EmploymentStatus)
def _employment_changed(sender, **kwargs):
    _invalidate(mc.RESOURCE_EMPLOYMENT_STATUSES)
