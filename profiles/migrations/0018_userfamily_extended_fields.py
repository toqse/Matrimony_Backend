from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0017_userprofile_birth_timezone'),
    ]

    operations = [
        migrations.AddField(
            model_name='userfamily',
            name='family_values',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='userfamily',
            name='native_place',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='userfamily',
            name='family_location',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='userfamily',
            name='family_contact',
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
