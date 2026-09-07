import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_dummyotpphone"),
        ("staff_mgmt", "0004_release_soft_deleted_mobiles"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="created_by_staff",
            field=models.ForeignKey(
                blank=True,
                help_text="Staff or branch-manager desk account that created this profile, if any.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_member_profiles",
                to="staff_mgmt.staffprofile",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="created_source",
            field=models.CharField(
                choices=[
                    ("website", "Website"),
                    ("staff", "Staff"),
                    ("admin", "Admin"),
                    ("branch_manager", "Branch Manager"),
                    ("bulk", "Bulk upload"),
                ],
                db_index=True,
                default="website",
                help_text="How this member profile was originally created.",
                max_length=20,
            ),
        ),
    ]
