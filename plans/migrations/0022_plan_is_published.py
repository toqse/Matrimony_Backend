from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("plans", "0021_perf_hotpath_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="is_published",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Show this plan on the website and allow online purchase. "
                    "Unpublished active plans are sold only via admin/staff/branch cash payment."
                ),
            ),
        ),
    ]
