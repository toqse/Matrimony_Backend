from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('profile_reports', '0002_unique_reporter_reported'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='profilereport',
            unique_together=set(),
        ),
    ]
