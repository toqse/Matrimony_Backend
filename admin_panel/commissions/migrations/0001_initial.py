from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("admin_auth", "0001_initial"),
        ("branches", "0001_initial"),
        ("plans", "0012_plan_is_highlighted"),
        ("staff_mgmt", "0002_alter_staffprofile_branch"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Commission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sale_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("commission_rate", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("commission_amt", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("paid", "Paid"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="approved_commissions",
                        to="admin_auth.adminuser",
                    ),
                ),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="commissions",
                        to="branches.branch",
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="commissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "staff",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="commissions",
                        to="staff_mgmt.staffprofile",
                    ),
                ),
                (
                    "subscription",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="commissions",
                        to="plans.userplan",
                    ),
                ),
            ],
            options={"db_table": "admin_commission", "ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="commission",
            index=models.Index(fields=["status"], name="admin_commi_status_3b2fb2_idx"),
        ),
        migrations.AddIndex(
            model_name="commission",
            index=models.Index(fields=["branch"], name="admin_commi_branch__8af8c8_idx"),
        ),
        migrations.AddIndex(
            model_name="commission",
            index=models.Index(fields=["staff"], name="admin_commi_staff_i_ec8fda_idx"),
        ),
        migrations.AddIndex(
            model_name="commission",
            index=models.Index(fields=["customer"], name="admin_commi_custome_9071d1_idx"),
        ),
    ]

