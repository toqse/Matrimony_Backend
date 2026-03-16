# UserFamily model; blood_group, children_count on UserPersonal; employment_status on UserEducation

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('profiles', '0004_userpersonal_height_text'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpersonal',
            name='blood_group',
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name='userpersonal',
            name='children_count',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='usereducation',
            name='employment_status',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.CreateModel(
            name='UserFamily',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('father_name', models.CharField(blank=True, max_length=150)),
                ('father_occupation', models.CharField(blank=True, max_length=150)),
                ('mother_name', models.CharField(blank=True, max_length=150)),
                ('mother_occupation', models.CharField(blank=True, max_length=150)),
                ('brothers', models.PositiveSmallIntegerField(default=0)),
                ('married_brothers', models.PositiveSmallIntegerField(default=0)),
                ('sisters', models.PositiveSmallIntegerField(default=0)),
                ('married_sisters', models.PositiveSmallIntegerField(default=0)),
                ('about_family', models.TextField(blank=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='user_family', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'profiles_user_family',
                'verbose_name_plural': 'User families',
            },
        ),
    ]
