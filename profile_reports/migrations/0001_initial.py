from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ProfileReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('message', models.TextField(max_length=2000)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('reviewed', 'Reviewed'),
                        ('dismissed', 'Dismissed'),
                    ],
                    db_index=True,
                    default='pending',
                    max_length=20,
                )),
                ('reporter', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='reports_made',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('reported', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='reports_received',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'profile_reports_profilereport',
                'ordering': ['-created_at'],
            },
        ),
    ]
