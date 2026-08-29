from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_perf_hotpath_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="reg_no",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Optional legacy registration number from bulk upload (not unique).",
                max_length=50,
            ),
        ),
    ]
