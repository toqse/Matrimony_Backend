from django.db import migrations


VALID_COMPLEXION_NAMES = (
    "Very Fair",
    "Fair",
    "Wheatish",
    "Dark",
)


def deactivate_invalid_complexions(apps, schema_editor):
    Complexion = apps.get_model("master", "Complexion")
    Complexion.objects.exclude(name__in=VALID_COMPLEXION_NAMES).update(is_active=False)
    for name in VALID_COMPLEXION_NAMES:
        obj, created = Complexion.objects.get_or_create(name=name, defaults={"is_active": True})
        if not created and not obj.is_active:
            obj.is_active = True
            obj.save(update_fields=["is_active", "updated_at"])
    try:
        from master.cache_utils import RESOURCE_COMPLEXIONS, invalidate_master_resource

        invalidate_master_resource(RESOURCE_COMPLEXIONS)
    except Exception:
        pass


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("master", "0009_complexion"),
    ]

    operations = [
        migrations.RunPython(deactivate_invalid_complexions, noop),
    ]
