from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("commissions", "0001_initial"),
        ("plans", "0012_plan_is_highlighted"),
    ]

    operations = [
        migrations.AlterField(
            model_name="commission",
            name="subscription",
            field=models.ForeignKey(
                blank=True,
                help_text="Set when commission is tied to a user subscription; null for manual entries.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="commissions",
                to="plans.userplan",
            ),
        ),
        migrations.AddField(
            model_name="commission",
            name="plan",
            field=models.ForeignKey(
                blank=True,
                help_text="Plan name for manual commissions when subscription is not linked.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="commissions",
                to="plans.plan",
            ),
        ),
    ]
