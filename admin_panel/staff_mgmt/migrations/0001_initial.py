from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("admin_auth", "0001_initial"),
        ("master", "0006_seed_education_subject_occupation_income"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("emp_code", models.CharField(db_index=True, max_length=20, unique=True)),
                ("name", models.CharField(max_length=150)),
                ("mobile", models.CharField(db_index=True, max_length=10, unique=True)),
                ("email", models.EmailField(blank=True, max_length=254, null=True, unique=True)),
                ("profile_photo", models.ImageField(blank=True, null=True, upload_to="staff/photos/")),
                ("designation", models.CharField(max_length=120)),
                ("department", models.CharField(blank=True, max_length=120)),
                ("joining_date", models.DateField(blank=True, null=True)),
                ("basic_salary", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("commission_rate", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("monthly_target", models.PositiveIntegerField(default=1)),
                ("achieved_target", models.PositiveIntegerField(default=0)),
                ("pf_number", models.CharField(blank=True, max_length=50)),
                ("esi_number", models.CharField(blank=True, max_length=50)),
                ("street_address", models.CharField(blank=True, max_length=255)),
                ("city", models.CharField(blank=True, max_length=100)),
                ("state", models.CharField(blank=True, max_length=100)),
                ("pincode", models.CharField(blank=True, max_length=10)),
                ("bank_name", models.CharField(blank=True, max_length=150)),
                ("account_number", models.CharField(blank=True, max_length=50)),
                ("ifsc_code", models.CharField(blank=True, max_length=20)),
                ("upi_id", models.CharField(blank=True, max_length=120)),
                ("login_username", models.CharField(blank=True, max_length=150, null=True, unique=True)),
                ("login_password_hash", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "admin_user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_profile",
                        to="admin_auth.adminuser",
                    ),
                ),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="staff_members",
                        to="master.branch",
                    ),
                ),
            ],
            options={"db_table": "admin_staff_profile", "ordering": ["-created_at"]},
        ),
    ]

