# UserSettings initial migration

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
            name='UserSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('profile_visibility', models.CharField(
                    choices=[
                        ('all_users', 'All users'),
                        ('premium_only', 'Premium users only'),
                        ('hidden', 'Hidden'),
                    ],
                    default='all_users',
                    max_length=20,
                )),
                ('interest_request_permission', models.CharField(
                    choices=[
                        ('all_users', 'All users'),
                        ('premium_only', 'Premium users only'),
                    ],
                    default='all_users',
                    max_length=20,
                )),
                ('notify_interest', models.BooleanField(default=True)),
                ('notify_chat', models.BooleanField(default=True)),
                ('notify_profile_views', models.BooleanField(default=True)),
                ('notify_new_matches', models.BooleanField(default=True)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='user_settings',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'user_settings_usersettings',
            },
        ),
    ]
