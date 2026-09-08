from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profile_reports', '0001_initial'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='profilereport',
            unique_together={('reporter', 'reported')},
        ),
    ]
