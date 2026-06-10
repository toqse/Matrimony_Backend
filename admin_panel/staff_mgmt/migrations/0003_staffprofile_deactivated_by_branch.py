from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("staff_mgmt", "0002_alter_staffprofile_branch"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffprofile",
            name="deactivated_by_branch",
            field=models.BooleanField(default=False),
        ),
    ]
