# Add Aadhaar front/back image fields to UserPhotos

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0006_partner_preference_structured'),
    ]

    operations = [
        migrations.AddField(
            model_name='userphotos',
            name='aadhaar_front',
            field=models.ImageField(blank=True, null=True, upload_to='profiles/aadhaar/%Y/%m/'),
        ),
        migrations.AddField(
            model_name='userphotos',
            name='aadhaar_back',
            field=models.ImageField(blank=True, null=True, upload_to='profiles/aadhaar/%Y/%m/'),
        ),
    ]
