# Generated manually for audit log enrichment

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit_log", "0004_alter_auditlog_action"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditlog",
            name="branch_name",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="staff_name",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="target_user_name",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="action_type",
            field=models.CharField(
                blank=True,
                choices=[("create", "Create"), ("update", "Update"), ("delete", "Delete")],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="endpoint",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("create", "Create"),
                    ("update", "Update"),
                    ("delete", "Delete"),
                    ("payment_create", "Payment Create"),
                    ("otp_verify", "OTP Verify"),
                    ("profile_update", "Profile Update"),
                    ("create_profile", "Create Profile"),
                    ("update_profile", "Update Profile"),
                    ("profile_verify", "Profile Verified"),
                    ("profile_unverify", "Profile Unverified"),
                    ("commission_create", "Commission Created"),
                    ("commission_update", "Commission Updated"),
                    ("branch_update", "Branch Updated"),
                    ("staff_update", "Staff Updated"),
                    ("subscription_update", "Subscription Updated"),
                    ("other", "Other"),
                ],
                max_length=50,
            ),
        ),
    ]
