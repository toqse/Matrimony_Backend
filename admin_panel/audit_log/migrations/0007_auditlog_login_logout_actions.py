from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit_log", "0006_staff_only_action_type_and_target_profile_name"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("login", "Login"),
                    ("logout", "Logout"),
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
