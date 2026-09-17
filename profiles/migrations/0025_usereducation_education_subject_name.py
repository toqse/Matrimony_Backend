# Generated manually for education subject combobox / manual subject fallback.

from django.db import migrations, models


def backfill_education_subject_name(apps, schema_editor):
    UserEducation = apps.get_model('profiles', 'UserEducation')
    for edu in (
        UserEducation.objects.filter(education_subject_id__isnull=False)
        .select_related('education_subject')
        .iterator()
    ):
        name = (getattr(edu.education_subject, 'name', None) or '').strip()
        if name and edu.education_subject_name != name:
            UserEducation.objects.filter(pk=edu.pk).update(education_subject_name=name)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0024_userlocation_city_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='usereducation',
            name='education_subject_name',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Free-text subject when no master EducationSubject is selected (City-style).',
                max_length=150,
            ),
        ),
        migrations.RunPython(backfill_education_subject_name, noop_reverse),
    ]
