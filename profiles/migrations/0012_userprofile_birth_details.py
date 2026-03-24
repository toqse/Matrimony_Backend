from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('profiles', '0011_bulk_upload_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='place_of_birth',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='time_of_birth',
            field=models.TimeField(blank=True, null=True),
        ),
    ]
