# Seed EducationSubject, Occupation, IncomeRange for profile education API

from django.db import migrations


STATIC_EDUCATION_SUBJECTS = [
    'Computer Science',
    'Information Technology',
    'Electronics',
    'Electrical',
    'Mechanical',
    'Civil',
    'Commerce',
    'Arts',
    'Science',
    'Mathematics',
    'Biology',
    'Chemistry',
    'Physics',
    'Business Administration',
    'Other',
]

STATIC_OCCUPATIONS = [
    'Software Engineer',
    'IT Professional',
    'Engineer',
    'Doctor',
    'Teacher',
    'Government Employee',
    'Business',
    'Self Employed',
    'Accountant',
    'Lawyer',
    'Architect',
    'Nurse',
    'Banking',
    'Other',
]

STATIC_INCOME_RANGES = [
    'Not Working',
    'Upto 1 Lakh',
    '1-2 Lakh',
    '2-5 Lakh',
    '5-10 Lakh',
    '10-15 Lakh',
    '15-25 Lakh',
    '25-50 Lakh',
    '50 Lakh & Above',
]


def seed_all(apps, schema_editor):
    EducationSubject = apps.get_model('master', 'EducationSubject')
    Occupation = apps.get_model('master', 'Occupation')
    IncomeRange = apps.get_model('master', 'IncomeRange')

    for name in STATIC_EDUCATION_SUBJECTS:
        EducationSubject.objects.get_or_create(name=name, defaults={'is_active': True})

    for name in STATIC_OCCUPATIONS:
        Occupation.objects.get_or_create(name=name, defaults={'is_active': True})

    for name in STATIC_INCOME_RANGES:
        IncomeRange.objects.get_or_create(name=name, defaults={'is_active': True})


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('master', '0005_seed_education_static'),
    ]

    operations = [
        migrations.RunPython(seed_all, noop),
    ]
