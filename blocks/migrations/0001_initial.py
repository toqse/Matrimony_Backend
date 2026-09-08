# Generated manually for blocks.UserBlock

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
            name='UserBlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('blocker', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='blocks_made',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('blocked', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='blocked_by',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'blocks_userblock',
                'unique_together': {('blocker', 'blocked')},
            },
        ),
    ]
