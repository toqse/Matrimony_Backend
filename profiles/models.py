"""
Profile models: UserProfile, UserLocation, UserReligion, UserPersonal, UserEducation, UserPhotos.
"""
from django.db import models
from django.conf import settings
from core.models import TimeStampedModel

__all__ = [
    'UserProfile',
    'UserLocation',
    'UserReligion',
    'UserPersonal',
    'UserFamily',
    'UserEducation',
    'UserPhotos',
]


class UserProfile(TimeStampedModel):
    """Main profile container; about_me stored here. Tracks multi-step completion."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_profile'
    )
    about_me = models.TextField(blank=True)

    # Multi-step profile completion flags
    location_completed = models.BooleanField(default=False)
    religion_completed = models.BooleanField(default=False)
    personal_completed = models.BooleanField(default=False)
    family_completed = models.BooleanField(default=False)
    education_completed = models.BooleanField(default=False)
    about_completed = models.BooleanField(default=False)
    photos_completed = models.BooleanField(default=False)

    admin_verified = models.BooleanField(
        default=False,
        help_text='Platform verification (admin). Distinct from mobile_verified.',
    )
    has_horoscope = models.BooleanField(
        default=False,
        help_text='Horoscope document available (admin/UI badge).',
    )
    horoscope_data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'profiles_user_profile'

    def __str__(self):
        return f'Profile of {self.user.matri_id}'


class UserLocation(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_location'
    )
    country = models.ForeignKey(
        'master.Country', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    state = models.ForeignKey(
        'master.State', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    district = models.ForeignKey(
        'master.District', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    city = models.ForeignKey(
        'master.City', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    address = models.TextField(blank=True)

    class Meta:
        db_table = 'profiles_user_location'

    def __str__(self):
        return f'Location of {self.user.matri_id}'


class UserReligion(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_religion'
    )
    religion = models.ForeignKey(
        'master.Religion', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    caste = models.CharField(max_length=100, blank=True)  # legacy free text; prefer caste_fk
    caste_fk = models.ForeignKey(
        'master.Caste', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    mother_tongue = models.ForeignKey(
        'master.MotherTongue', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    partner_religion_preference = models.CharField(max_length=255, blank=True)
    # Structured partner preference (matches depend on these)
    PARTNER_PREFERENCE_OWN = 'own_religion_only'
    PARTNER_PREFERENCE_ALL = 'open_to_all'
    PARTNER_PREFERENCE_SPECIFIC = 'specific_religions'
    PARTNER_PREFERENCE_TYPE_CHOICES = [
        (PARTNER_PREFERENCE_OWN, 'Own religion only'),
        (PARTNER_PREFERENCE_ALL, 'Open to all religions'),
        (PARTNER_PREFERENCE_SPECIFIC, 'Specific religions'),
    ]
    partner_preference_type = models.CharField(
        max_length=30, choices=PARTNER_PREFERENCE_TYPE_CHOICES,
        default=PARTNER_PREFERENCE_ALL, blank=True
    )
    partner_religion_ids = models.JSONField(default=list, blank=True)  # list of Religion IDs when type is specific_religions
    PARTNER_CASTE_ANY = 'any'
    PARTNER_CASTE_OWN = 'own_caste_only'
    PARTNER_CASTE_CHOICES = [
        (PARTNER_CASTE_ANY, 'Any'),
        (PARTNER_CASTE_OWN, 'Own caste only'),
    ]
    partner_caste_preference = models.CharField(
        max_length=20, choices=PARTNER_CASTE_CHOICES,
        default=PARTNER_CASTE_ANY, blank=True
    )
    gothram = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = 'profiles_user_religion'

    def __str__(self):
        return f'Religion of {self.user.matri_id}'


class UserPersonal(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_personal'
    )
    marital_status = models.ForeignKey(
        'master.MaritalStatus', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    has_children = models.BooleanField(default=False)
    height = models.ForeignKey(
        'master.Height', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    height_text = models.CharField(max_length=50, blank=True, help_text='Free-text height, e.g. 5\'6", 170 cm')
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    colour = models.CharField(max_length=50, blank=True)
    blood_group = models.CharField(max_length=10, blank=True)
    number_of_children = models.PositiveSmallIntegerField(default=0, db_column='children_count')
    children_living_with = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'profiles_user_personal'

    def __str__(self):
        return f'Personal of {self.user.matri_id}'


class UserFamily(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_family'
    )
    father_name = models.CharField(max_length=150, blank=True)
    father_occupation = models.CharField(max_length=150, blank=True)
    mother_name = models.CharField(max_length=150, blank=True)
    mother_occupation = models.CharField(max_length=150, blank=True)
    brothers = models.PositiveSmallIntegerField(default=0)
    married_brothers = models.PositiveSmallIntegerField(default=0)
    sisters = models.PositiveSmallIntegerField(default=0)
    married_sisters = models.PositiveSmallIntegerField(default=0)
    about_family = models.TextField(blank=True)
    family_type = models.CharField(max_length=100, blank=True)
    family_status = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'profiles_user_family'
        verbose_name_plural = 'User families'

    def __str__(self):
        return f'Family of {self.user.matri_id}'


class UserEducation(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_education'
    )
    highest_education = models.ForeignKey(
        'master.Education', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    education_subject = models.ForeignKey(
        'master.EducationSubject', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    occupation = models.ForeignKey(
        'master.Occupation', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    annual_income = models.ForeignKey(
        'master.IncomeRange', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    employment_status = models.CharField(max_length=50, blank=True)
    company = models.CharField(max_length=200, blank=True)
    working_location = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'profiles_user_education'

    def __str__(self):
        return f'Education of {self.user.matri_id}'


class UserPhotos(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_photos'
    )
    profile_photo = models.ImageField(upload_to='profiles/%Y/%m/', null=True, blank=True)
    full_photo = models.ImageField(upload_to='profiles/%Y/%m/', null=True, blank=True)
    selfie_photo = models.ImageField(upload_to='profiles/%Y/%m/', null=True, blank=True)
    family_photo = models.ImageField(upload_to='profiles/%Y/%m/', null=True, blank=True)
    aadhaar_front = models.ImageField(upload_to='profiles/aadhaar/%Y/%m/', null=True, blank=True)
    aadhaar_back = models.ImageField(upload_to='profiles/aadhaar/%Y/%m/', null=True, blank=True)
    profile_photo_url = models.URLField(max_length=500, blank=True)

    class Meta:
        db_table = 'profiles_user_photos'
        verbose_name_plural = 'User photos'

    def __str__(self):
        return f'Photos of {self.user.matri_id}'
