from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0018_userfamily_extended_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='userfamily',
            name='family_contact_2',
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
