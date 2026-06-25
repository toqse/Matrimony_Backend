from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0021_userfamily_sibling_counts_nullable'),
    ]

    operations = [
        migrations.AddField(
            model_name='userpersonal',
            name='reason_for_divorce',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
