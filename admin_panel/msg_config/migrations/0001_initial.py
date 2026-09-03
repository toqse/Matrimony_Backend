from django.db import migrations, models


def create_default_config(apps, schema_editor):
    MsgConfig = apps.get_model("admin_msg_config", "MsgConfig")
    MsgConfig.objects.get_or_create(
        pk=1,
        defaults={
            "development_mode": True,
            "auth_key": "",
            "integrated_number": "918590123876",
            "namespace": "2a0ae24e_63d6_47b2_85f4_b18d0d9e2acb",
        },
    )


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="MsgConfig",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        db_column="singleton_id",
                        default=1,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "development_mode",
                    models.BooleanField(
                        default=True,
                        help_text="When True, skip real MSG91 sends and expose OTPs for autofill.",
                    ),
                ),
                (
                    "auth_key",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="MSG91 authkey. Blank falls back to MSG91_AUTH_KEY env.",
                        max_length=255,
                    ),
                ),
                (
                    "integrated_number",
                    models.CharField(blank=True, default="918590123876", max_length=20),
                ),
                (
                    "namespace",
                    models.CharField(
                        blank=True,
                        default="2a0ae24e_63d6_47b2_85f4_b18d0d9e2acb",
                        max_length=64,
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "MSG config",
                "db_table": "msg_config",
            },
        ),
        migrations.RunPython(create_default_config, migrations.RunPython.noop),
    ]
