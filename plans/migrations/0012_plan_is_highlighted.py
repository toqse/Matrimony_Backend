from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("plans", "0011_merge_0010s"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="is_highlighted",
            field=models.BooleanField(
                default=False,
                help_text="Show this plan prominently on user-facing plans page.",
            ),
        ),
    ]

