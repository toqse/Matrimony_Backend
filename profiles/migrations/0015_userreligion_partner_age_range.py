from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0014_userfamily_parent_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='userreligion',
            name='partner_age_from',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='userreligion',
            name='partner_age_to',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
