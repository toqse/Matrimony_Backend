from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("branches", "0001_initial"),
        ("staff_mgmt", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="staffprofile",
            name="branch",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="staff_members",
                to="branches.branch",
            ),
        ),
    ]

