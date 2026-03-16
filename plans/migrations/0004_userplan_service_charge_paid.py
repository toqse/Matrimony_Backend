# Add service_charge_paid for split payment (499 first, 14501 remaining)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('plans', '0003_seed_three_plans'),
    ]

    operations = [
        migrations.AddField(
            model_name='userplan',
            name='service_charge_paid',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Amount of service charge paid so far (first payment 499, then remaining 14501)',
                max_digits=12,
            ),
        ),
    ]
