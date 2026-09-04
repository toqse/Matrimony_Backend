import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_user_reg_no"),
    ]

    operations = [
        migrations.CreateModel(
            name="DummyOTPPhone",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "phone",
                    models.CharField(
                        db_index=True,
                        help_text="E.164 Indian mobile, e.g. +919876543210",
                        max_length=20,
                        unique=True,
                    ),
                ),
                (
                    "dummy_otp",
                    models.CharField(
                        help_text="Fixed OTP that also works for this phone (digits only).",
                        max_length=10,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("note", models.CharField(blank=True, default="", max_length=255)),
            ],
            options={
                "verbose_name": "Dummy OTP phone",
                "verbose_name_plural": "Dummy OTP phones",
                "db_table": "accounts_dummy_otp_phone",
                "ordering": ["-updated_at"],
            },
        ),
    ]
