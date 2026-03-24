from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('profiles', '0012_userprofile_birth_details'),
    ]

    operations = [
        migrations.CreateModel(
            name='Horoscope',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('date_of_birth', models.DateField()),
                ('time_of_birth', models.TimeField()),
                ('place_of_birth', models.CharField(max_length=255)),
                ('latitude', models.FloatField()),
                ('longitude', models.FloatField()),
                ('lagna', models.CharField(max_length=50)),
                ('rasi', models.CharField(max_length=50)),
                ('nakshatra', models.CharField(max_length=50)),
                ('nakshatra_pada', models.PositiveSmallIntegerField()),
                ('gana', models.CharField(max_length=50)),
                ('yoni', models.CharField(max_length=50)),
                ('nadi', models.CharField(max_length=50)),
                ('rajju', models.CharField(max_length=50)),
                ('grahanila', models.JSONField(blank=True, default=dict)),
                ('birth_input_hash', models.CharField(db_index=True, max_length=64)),
                ('profile', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='horoscope', to='profiles.userprofile')),
            ],
            options={
                'db_table': 'astrology_horoscope',
            },
        ),
    ]
