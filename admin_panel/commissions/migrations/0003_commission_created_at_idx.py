from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("commissions", "0002_commission_manual_plan_and_nullable_subscription"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="commission",
            index=models.Index(fields=["-created_at"], name="admin_commission_created_desc"),
        ),
    ]
