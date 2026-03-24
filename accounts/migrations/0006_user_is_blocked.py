from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_tokens_invalid_before"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_blocked",
            field=models.BooleanField(default=False, help_text="Blocked by admin; cannot use the app."),
        ),
    ]
