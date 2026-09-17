from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_backfill_user_created_by"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="otprecord",
            options={
                "ordering": ["-created_at"],
                "verbose_name": "OTP record",
                "verbose_name_plural": "OTP records",
            },
        ),
        migrations.AddField(
            model_name="otprecord",
            name="otp_code",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Plaintext OTP for Django admin visibility only (not returned by APIs).",
                max_length=10,
            ),
        ),
    ]
