# Generated manually for city combobox / manual city fallback.

from django.db import migrations, models


def backfill_city_name(apps, schema_editor):
    UserLocation = apps.get_model('profiles', 'UserLocation')
    for loc in UserLocation.objects.filter(city_id__isnull=False).select_related('city').iterator():
        name = (getattr(loc.city, 'name', None) or '').strip()
        if name and loc.city_name != name:
            UserLocation.objects.filter(pk=loc.pk).update(city_name=name)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0023_perf_hotpath_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='userlocation',
            name='city_name',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.RunPython(backfill_city_name, noop_reverse),
    ]
