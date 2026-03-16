# Female service charge: 10000 (so remaining after 499 = 9501). Male stays 15000 (remaining 14501).

from decimal import Decimal
from django.db import migrations


def set_female_service_charge(apps, schema_editor):
    ServiceCharge = apps.get_model('plans', 'ServiceCharge')
    ServiceCharge.objects.filter(gender='F').update(amount=Decimal('10000'))


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('plans', '0004_userplan_service_charge_paid'),
    ]

    operations = [
        migrations.RunPython(set_female_service_charge, noop),
    ]
