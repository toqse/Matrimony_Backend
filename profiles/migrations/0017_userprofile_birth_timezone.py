from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0016_add_birth_coordinates'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='birth_timezone',
            field=models.FloatField(
                blank=True,
                null=True,
                help_text='UTC offset in hours used for horoscope generation (e.g. 5.5 for IST).',
            ),
        ),
    ]
