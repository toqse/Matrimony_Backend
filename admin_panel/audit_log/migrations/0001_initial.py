from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("admin_auth", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("actor_name", models.CharField(blank=True, max_length=150)),
                ("actor_role", models.CharField(blank=True, max_length=20)),
                (
                    "action",
                    models.CharField(
                        choices=[
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
                ("resource", models.CharField(max_length=255)),
                ("details", models.TextField(blank=True)),
                ("old_value", models.JSONField(blank=True, null=True)),
                ("new_value", models.JSONField(blank=True, null=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to="admin_auth.adminuser",
                    ),
                ),
            ],
            options={
                "db_table": "admin_audit_log",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["-created_at"], name="admin_audit__created_71467f_idx"),
                    models.Index(fields=["action"], name="admin_audit_action_612bc2_idx"),
                    models.Index(fields=["actor_role"], name="admin_audit_actor_r_6f21cc_idx"),
                ],
            },
        ),
    ]
