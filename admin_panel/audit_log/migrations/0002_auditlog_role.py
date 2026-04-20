from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audit_log", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditlog",
            name="role",
            field=models.CharField(
                blank=True,
                choices=[
                    ("admin", "Admin"),
                    ("staff", "Staff"),
                    ("branch_manager", "Branch Manager"),
                ],
                max_length=20,
            ),
        ),
    ]

