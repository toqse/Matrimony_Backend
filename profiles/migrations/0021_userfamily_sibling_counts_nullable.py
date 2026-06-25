from django.db import migrations, models


def clear_default_sibling_counts(apps, schema_editor):
    UserFamily = apps.get_model('profiles', 'UserFamily')
    for field in ('brothers', 'married_brothers', 'sisters', 'married_sisters'):
        UserFamily.objects.filter(**{field: 0}).update(**{field: None})


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0020_userfamily_sibling_occupations'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userfamily',
            name='brothers',
            field=models.PositiveSmallIntegerField(blank=True, default=None, null=True),
        ),
        migrations.AlterField(
            model_name='userfamily',
            name='married_brothers',
            field=models.PositiveSmallIntegerField(blank=True, default=None, null=True),
        ),
        migrations.AlterField(
            model_name='userfamily',
            name='sisters',
            field=models.PositiveSmallIntegerField(blank=True, default=None, null=True),
        ),
        migrations.AlterField(
            model_name='userfamily',
            name='married_sisters',
            field=models.PositiveSmallIntegerField(blank=True, default=None, null=True),
        ),
        migrations.RunPython(clear_default_sibling_counts, migrations.RunPython.noop),
    ]
