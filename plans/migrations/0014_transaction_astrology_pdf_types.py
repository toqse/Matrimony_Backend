from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('plans', '0013_transaction_type_created_idx'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transaction',
            name='transaction_type',
            field=models.CharField(
                choices=[
                    ('plan_purchase', 'Plan Purchase'),
                    ('profile_boost', 'Profile Boost'),
                    ('refund', 'Refund'),
                    ('jathakam_pdf', 'Jathakam PDF'),
                    ('thalakuri_pdf', 'Thalakuri PDF'),
                ],
                default='plan_purchase',
                max_length=20,
            ),
        ),
    ]
