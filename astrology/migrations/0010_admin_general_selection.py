# Generated manually for admin general partner selections (no porutham).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admin_auth', '0002_adminuser_email'),
        ('astrology', '0009_admin_saved_porutham_match'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AdminGeneralSelection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('mode', models.CharField(choices=[('fixed_bride', 'Fixed bride'), ('fixed_groom', 'Fixed groom')], max_length=20)),
                ('fixed_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='admin_general_selection_as_fixed', to=settings.AUTH_USER_MODEL)),
                ('partner_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='admin_general_selection_as_partner', to=settings.AUTH_USER_MODEL)),
                ('saved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='saved_general_selections', to='admin_auth.adminuser')),
            ],
            options={
                'db_table': 'admin_general_selection',
            },
        ),
        migrations.AddIndex(
            model_name='admingeneralselection',
            index=models.Index(fields=['fixed_user', '-updated_at'], name='admin_gen_sel_fixed_idx'),
        ),
        migrations.AddConstraint(
            model_name='admingeneralselection',
            constraint=models.UniqueConstraint(fields=('fixed_user', 'partner_user'), name='uniq_admin_general_selection_fixed_partner'),
        ),
    ]
