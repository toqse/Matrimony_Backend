from decimal import Decimal
from django.db import migrations


def fix_service_charge_amounts(apps, schema_editor):
    """
    Ensure service charges match product rules:
    - Male   : 15000
    - Female : 10000
    (Create rows if missing, and update existing rows.)
    """
    ServiceCharge = apps.get_model("plans", "ServiceCharge")

    desired = {
        "M": Decimal("15000"),
        "F": Decimal("10000"),
    }

    for gender, amount in desired.items():
        obj, created = ServiceCharge.objects.get_or_create(
            gender=gender, defaults={"amount": amount}
        )
        if not created and obj.amount != amount:
            ServiceCharge.objects.filter(pk=obj.pk).update(amount=amount)


class Migration(migrations.Migration):
    dependencies = [
        ("plans", "0009_unique_profile_view_pair"),
    ]

    operations = [
        migrations.RunPython(fix_service_charge_amounts, migrations.RunPython.noop),
    ]

