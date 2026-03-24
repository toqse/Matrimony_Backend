from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("plans", "0012_plan_is_highlighted"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(
                fields=["transaction_type", "-created_at"],
                name="plans_txn_type_created_desc",
            ),
        ),
    ]
