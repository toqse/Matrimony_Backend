from django.db import migrations, models


def create_default_config(apps, schema_editor):
    MobileAppConfig = apps.get_model("admin_app_config", "MobileAppConfig")
    MobileAppConfig.objects.get_or_create(
        pk=1,
        defaults={
            "android_version": "1.0.0",
            "ios_version": "1.0.0",
            "android_force_update": False,
            "ios_force_update": False,
        },
    )


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="MobileAppConfig",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("android_version", models.CharField(default="1.0.0", max_length=32)),
                ("ios_version", models.CharField(default="1.0.0", max_length=32)),
                ("android_force_update", models.BooleanField(default=False)),
                ("ios_force_update", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Mobile app config",
                "db_table": "mobile_app_config",
            },
        ),
        migrations.RunPython(create_default_config, migrations.RunPython.noop),
    ]
