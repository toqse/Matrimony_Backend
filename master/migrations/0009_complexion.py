from django.db import migrations, models


DEFAULT_COMPLEXIONS = [
    "Very Fair",
    "Fair",
    "Wheatish",
    "Wheatish Brown",
    "Dark",
    "Other",
]


def seed_default_complexions(apps, schema_editor):
    Complexion = apps.get_model("master", "Complexion")
    for name in DEFAULT_COMPLEXIONS:
        Complexion.objects.get_or_create(name=name, defaults={"is_active": True})


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("master", "0008_seed_employment_and_education_subject_map"),
    ]

    operations = [
        migrations.CreateModel(
            name="Complexion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=50, unique=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "master_complexion",
                "ordering": ["name"],
            },
        ),
        migrations.RunPython(seed_default_complexions, noop),
    ]
