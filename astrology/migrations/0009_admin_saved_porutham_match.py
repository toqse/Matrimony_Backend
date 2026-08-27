# Generated manually for admin saved porutham matches

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admin_auth', '0002_adminuser_email'),
        ('astrology', '0008_perf_hotpath_indexes'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AdminSavedPoruthamMatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('mode', models.CharField(choices=[('fixed_bride', 'Fixed bride'), ('fixed_groom', 'Fixed groom')], max_length=20)),
                ('score', models.IntegerField(default=0)),
                ('max_score', models.IntegerField(default=10)),
                ('overall_result', models.CharField(blank=True, max_length=20)),
                ('uthamam_count', models.IntegerField(blank=True, null=True)),
                ('porutham_snapshot', models.JSONField(blank=True, null=True)),
                ('fixed_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='admin_saved_porutham_as_fixed', to=settings.AUTH_USER_MODEL)),
                ('partner_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='admin_saved_porutham_as_partner', to=settings.AUTH_USER_MODEL)),
                ('saved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='saved_porutham_matches', to='admin_auth.adminuser')),
            ],
            options={
                'db_table': 'admin_saved_porutham_match',
            },
        ),
        migrations.AddIndex(
            model_name='adminsavedporuthammatch',
            index=models.Index(fields=['fixed_user', '-updated_at'], name='admin_saved_porutham_fixed_idx'),
        ),
        migrations.AddConstraint(
            model_name='adminsavedporuthammatch',
            constraint=models.UniqueConstraint(fields=('fixed_user', 'partner_user'), name='uniq_admin_saved_porutham_fixed_partner'),
        ),
    ]
