from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0009_merge_0008_and_family"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="admin_verified",
            field=models.BooleanField(
                default=False,
                help_text="Platform verification (admin). Distinct from mobile_verified.",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="has_horoscope",
            field=models.BooleanField(
                default=False,
                help_text="Horoscope document available (admin/UI badge).",
            ),
        ),
    ]
