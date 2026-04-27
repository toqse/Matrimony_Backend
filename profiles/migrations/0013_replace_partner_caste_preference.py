from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0012_userprofile_birth_details'),
    ]

    operations = [
        migrations.AddField(
            model_name='userreligion',
            name='partner_caste_preferences',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RemoveField(
            model_name='userreligion',
            name='partner_caste_preference',
        ),
    ]
