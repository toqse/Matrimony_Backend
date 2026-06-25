from django.db import migrations, models


def _column_exists(cursor, table, column, vendor):
    if vendor == "mysql":
        cursor.execute(
            """
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
            """,
            [table, column],
        )
        return cursor.fetchone()[0] > 0
    if vendor == "sqlite":
        cursor.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cursor.fetchall())
    return False


def align_singleton_id_column(apps, schema_editor):
    table = "mobile_app_config"
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        has_singleton = _column_exists(cursor, table, "singleton_id", vendor)
        has_id = _column_exists(cursor, table, "id", vendor)
        if has_id and not has_singleton:
            if vendor == "mysql":
                cursor.execute(
                    "ALTER TABLE mobile_app_config "
                    "CHANGE id singleton_id SMALLINT UNSIGNED NOT NULL"
                )
            elif vendor == "sqlite":
                cursor.execute(
                    "ALTER TABLE mobile_app_config "
                    "RENAME COLUMN id TO singleton_id"
                )


def seed_default_config(apps, schema_editor):
    MobileAppConfig = apps.get_model("admin_app_config", "MobileAppConfig")
    if not MobileAppConfig.objects.exists():
        MobileAppConfig.objects.create(
            id=1,
            android_version="1.0.0",
            ios_version="1.0.0",
            android_force_update=False,
            ios_force_update=False,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("admin_app_config", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="mobileappconfig",
                    name="id",
                    field=models.PositiveSmallIntegerField(
                        db_column="singleton_id",
                        default=1,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(align_singleton_id_column, migrations.RunPython.noop),
        migrations.RunPython(seed_default_config, migrations.RunPython.noop),
    ]
