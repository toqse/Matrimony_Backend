# ProfileView: last_viewed_at for home-slider ordering (re-touches change sort)

import django.utils.timezone
from django.db import migrations, models


def backfill_last_viewed_at(apps, schema_editor):
    """Align with first-seen time so existing rows sort sensibly; new touches will update the field."""
    ProfileView = apps.get_model("plans", "ProfileView")
    for pv in ProfileView.objects.all().only("id", "created_at").iterator():
        if pv.created_at is not None:
            ProfileView.objects.filter(pk=pv.pk).update(last_viewed_at=pv.created_at)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("plans", "0017_alter_profileview_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="profileview",
            name="last_viewed_at",
            field=models.DateTimeField(
                default=django.utils.timezone.now,
                help_text="Updated on every profile view; used for home-slider ordering among already-viewed profiles.",
            ),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_last_viewed_at, noop),
    ]
