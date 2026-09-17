# Generated manually for occupation free-text + occupation_search filters.

from django.db import migrations, models


def backfill_occupation_name(apps, schema_editor):
    UserEducation = apps.get_model('profiles', 'UserEducation')
    for edu in (
        UserEducation.objects.filter(occupation_id__isnull=False)
        .select_related('occupation')
        .iterator()
    ):
        name = (getattr(edu.occupation, 'name', None) or '').strip()
        if name and edu.occupation_name != name:
            UserEducation.objects.filter(pk=edu.pk).update(occupation_name=name[:100])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0025_usereducation_education_subject_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='usereducation',
            name='occupation_name',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Free-text occupation when no master Occupation is selected.',
                max_length=100,
            ),
        ),
        migrations.RunPython(backfill_occupation_name, noop_reverse),
    ]
