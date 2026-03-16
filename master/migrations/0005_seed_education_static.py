# Seed Education (highest education) with static list; live search via GET /educations/?search=

from django.db import migrations


# Static list of highest education options (matrimony profile)
STATIC_EDUCATION = [
    'Below 10th',
    '10th',
    '12th',
    'Diploma',
    'B.A.',
    'B.Com.',
    'B.Ed.',
    'B.Sc.',
    'B.Tech.',
    'B.E.',
    'BBA',
    'BCA',
    'LLB',
    'MBBS',
    'BDS',
    'B.Pharm',
    'M.A.',
    'M.Com.',
    'M.Sc.',
    'M.Tech.',
    'M.E.',
    'MBA',
    'MCA',
    'M.Ed.',
    'MS',
    'MD',
    'MDS',
    'M.Pharm',
    'LLM',
    'CA',
    'CS',
    'ICWA',
    'PhD',
    'Other',
]


def seed_education(apps, schema_editor):
    Education = apps.get_model('master', 'Education')
    existing = set(Education.objects.values_list('name', flat=True))
    for name in STATIC_EDUCATION:
        if name not in existing:
            Education.objects.create(name=name, is_active=True)
            existing.add(name)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('master', '0004_seed_marital_status'),
    ]

    operations = [
        migrations.RunPython(seed_education, noop),
    ]
