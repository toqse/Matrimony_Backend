"""
Master/reference models: Country, State, District, City, Religion, etc.
"""
from django.db import models
from core.models import TimeStampedModel


class Country(TimeStampedModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'master_country'
        ordering = ['name']
        verbose_name_plural = 'Countries'

    def __str__(self):
        return self.name


class State(TimeStampedModel):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='states')
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'master_state'
        ordering = ['name']
        unique_together = [['country', 'name']]

    def __str__(self):
        return f'{self.name}, {self.country.name}'


class District(TimeStampedModel):
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name='districts')
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'master_district'
        ordering = ['name']
        unique_together = [['state', 'name']]

    def __str__(self):
        return f'{self.name}, {self.state.name}'


class City(TimeStampedModel):
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name='cities')
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'master_city'
        ordering = ['name']
        unique_together = [['district', 'name']]
        verbose_name_plural = 'Cities'

    def __str__(self):
        return f'{self.name}, {self.district.name}'


class Religion(TimeStampedModel):
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'master_religion'
        ordering = ['name']

    def __str__(self):
        return self.name


class Caste(TimeStampedModel):
    religion = models.ForeignKey(
        Religion, on_delete=models.CASCADE, related_name='castes'
    )
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'master_caste'
        ordering = ['name']
        unique_together = [['religion', 'name']]

    def __str__(self):
        return f'{self.name} ({self.religion.name})'


class MotherTongue(TimeStampedModel):
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'master_mother_tongue'
        ordering = ['name']

    def __str__(self):
        return self.name


class Height(TimeStampedModel):
    """Height in cm, with optional display label (e.g. 5'6\")"""
    value_cm = models.PositiveSmallIntegerField(help_text='Height in centimetres')
    display_label = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'master_height'
        ordering = ['value_cm']

    def __str__(self):
        return self.display_label or f'{self.value_cm} cm'


class MaritalStatus(TimeStampedModel):
    name = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'master_marital_status'
        ordering = ['name']
        verbose_name_plural = 'Marital statuses'

    def __str__(self):
        return self.name


class IncomeRange(TimeStampedModel):
    name = models.CharField(max_length=100)
    min_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    max_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'master_income_range'
        ordering = ['min_value']

    def __str__(self):
        return self.name


class Education(TimeStampedModel):
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'master_education'
        ordering = ['name']

    def __str__(self):
        return self.name


class EducationSubject(TimeStampedModel):
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'master_education_subject'
        ordering = ['name']

    def __str__(self):
        return self.name


class Occupation(TimeStampedModel):
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'master_occupation'
        ordering = ['name']

    def __str__(self):
        return self.name


class Branch(TimeStampedModel):
    """Branch for staff/branch manager data isolation."""
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'master_branch'
        ordering = ['name']
        verbose_name_plural = 'Branches'

    def __str__(self):
        return self.name
