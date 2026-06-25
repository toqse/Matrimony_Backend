from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0019_userfamily_contact_2'),
    ]

    operations = [
        migrations.AddField(
            model_name='userfamily',
            name='brother_occupation',
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name='userfamily',
            name='sister_occupation',
            field=models.CharField(blank=True, max_length=150),
        ),
    ]
