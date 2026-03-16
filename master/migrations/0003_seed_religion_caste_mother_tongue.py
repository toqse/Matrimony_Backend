# Data migration: seed minimal Religion, Caste, MotherTongue for dropdown/profile use

from django.db import migrations


def seed_minimal(apps, schema_editor):
    Religion = apps.get_model('master', 'Religion')
    Caste = apps.get_model('master', 'Caste')
    MotherTongue = apps.get_model('master', 'MotherTongue')
    if Religion.objects.count() == 0:
        Religion.objects.create(name='Hinduism', is_active=True)
        Religion.objects.create(name='Islam', is_active=True)
        Religion.objects.create(name='Christianity', is_active=True)
    if MotherTongue.objects.count() == 0:
        MotherTongue.objects.create(name='Malayalam', is_active=True)
        MotherTongue.objects.create(name='Hindi', is_active=True)
        MotherTongue.objects.create(name='Tamil', is_active=True)
    if Caste.objects.count() == 0 and Religion.objects.filter(name='Hinduism').exists():
        r = Religion.objects.get(name='Hinduism')
        Caste.objects.create(religion=r, name='Ezhava', is_active=True)
        Caste.objects.create(religion=r, name='Nair', is_active=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('master', '0002_caste'),
    ]

    operations = [
        migrations.RunPython(seed_minimal, noop),
    ]
