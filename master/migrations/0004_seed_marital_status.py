# Seed MaritalStatus with common values for profile personal API

from django.db import migrations


def seed_marital_status(apps, schema_editor):
    MaritalStatus = apps.get_model('master', 'MaritalStatus')
    if MaritalStatus.objects.exists():
        return
    for name in [
        'Never Married',
        'Married',
        'Widowed',
        'Divorced',
        'Separated',
        'Awaiting Divorce',
    ]:
        MaritalStatus.objects.create(name=name, is_active=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('master', '0003_seed_religion_caste_mother_tongue'),
    ]

    operations = [
        migrations.RunPython(seed_marital_status, noop),
    ]
