# Add height_text for free-text height (no dropdown)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0003_userreligion_caste_fk'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpersonal',
            name='height_text',
            field=models.CharField(blank=True, help_text="Free-text height, e.g. 5'6\", 170 cm", max_length=50),
        ),
    ]
