from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("admin_auth", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="adminuser",
            name="email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
    ]
