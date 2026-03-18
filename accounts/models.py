"""
User model and OTP storage (DB fallback).
"""
import uuid
import re
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from core.models import TimeStampedModel


def _generate_matri_id():
    """Generate next Matri ID in format AM100001, AM100002, ..."""
    from django.db.models import Max
    prefix = 'AM'
    last = User.objects.aggregate(m=Max('matri_id'))['m']
    if not last or not re.match(r'^AM(\d+)$', last):
        num = 100001
    else:
        num = int(re.match(r'^AM(\d+)$', last).group(1)) + 1
    return f'{prefix}{num}'


class UserManager(BaseUserManager):
    def create_user(self, email=None, mobile=None, password=None, **kwargs):
        if not email and not mobile:
            raise ValueError('User must have email or mobile.')
        email = (email or '').strip()
        mobile = (mobile or '').strip()
        if email:
            email = self.normalize_email(email)
        # For optional fields with unique=True, store NULL (None) instead of empty string
        email = email or None
        mobile = mobile or None
        user = self.model(email=email, mobile=mobile, **kwargs)
        user.set_password(password or self.make_random_password())
        if not getattr(user, 'matri_id', None):
            user.matri_id = _generate_matri_id()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **kwargs):
        kwargs.setdefault('is_staff', True)
        kwargs.setdefault('is_superuser', True)
        kwargs.setdefault('is_active', True)  # required for Django admin login
        kwargs.setdefault('role', 'admin')
        kwargs['role'] = 'admin'
        return self.create_user(email=email, password=password, **kwargs)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('staff', 'Staff'),
        ('branch_manager', 'Branch Manager'),
        ('admin', 'Admin'),
    ]
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]
    PROFILE_FOR_CHOICES = [
        ('myself', 'Myself'),
        ('son', 'Son'),
        ('daughter', 'Daughter'),
        ('brother', 'Brother'),
        ('sister', 'Sister'),
        ('friend', 'Friend'),
        ('relative', 'Relative'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    matri_id = models.CharField(max_length=20, unique=True, editable=False, db_index=True, null=True, blank=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    mobile = models.CharField(max_length=20, unique=True, null=True, blank=True, db_index=True)
    password = models.CharField(max_length=128)
    name = models.CharField(max_length=150, blank=True)
    dob = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    profile_for = models.CharField(
        max_length=20,
        choices=PROFILE_FOR_CHOICES,
        null=True,
        blank=True,
        help_text='Who the profile is being registered for (e.g. Myself, Son, Daughter)',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    branch = models.ForeignKey(
        'master.Branch', on_delete=models.SET_NULL, null=True, blank=True, related_name='users'
    )
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    mobile_verified = models.BooleanField(default=False)
    is_registration_profile_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen = models.DateTimeField(null=True, blank=True, help_text='Last activity for online status')
    tokens_invalid_before = models.DateTimeField(
        null=True,
        blank=True,
        help_text='If set, reject JWTs issued before this time (e.g. after logout).',
    )

    objects = UserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'accounts_user'

    def __str__(self):
        return self.matri_id or self.email or self.mobile or str(self.id)

    @property
    def is_subscribed(self):
        return False

    @property
    def phone_number(self):
        return self.mobile or ''

    def save(self, *args, **kwargs):
        if not self.matri_id or (isinstance(self.matri_id, str) and not self.matri_id.strip()):
            self.matri_id = _generate_matri_id()
        super().save(*args, **kwargs)


class OTPRecord(TimeStampedModel):
    """DB fallback for OTP when Redis unavailable."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    identifier = models.CharField(max_length=255, db_index=True)
    otp_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    verified = models.BooleanField(default=False)

    class Meta:
        db_table = 'accounts_otp_record'
