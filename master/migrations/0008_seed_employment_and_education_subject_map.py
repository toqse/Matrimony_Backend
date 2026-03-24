from django.db import migrations


EMPLOYMENT_STATUSES = [
    'Employed',
    'Self-Employed',
    'Business',
    'Government Employee',
    'Private Employee',
    'Student',
    'Not Working',
    'Other',
]


def _norm(value):
    return (value or '').strip().lower().rstrip('.')


def seed_employment_and_subject_map(apps, schema_editor):
    Education = apps.get_model('master', 'Education')
    EducationSubject = apps.get_model('master', 'EducationSubject')
    EmploymentStatus = apps.get_model('master', 'EmploymentStatus')

    for name in EMPLOYMENT_STATUSES:
        EmploymentStatus.objects.get_or_create(name=name, defaults={'is_active': True})

    education_map = {
        _norm(e.name): e.id
        for e in Education.objects.filter(is_active=True)
    }
    subject_map = {
        _norm(s.name): s.id
        for s in EducationSubject.objects.filter(is_active=True)
    }

    education_subject_map = {
        'below 10th': ['science', 'mathematics', 'biology', 'chemistry', 'physics', 'other'],
        '10th': ['science', 'mathematics', 'biology', 'chemistry', 'physics', 'other'],
        '12th': ['science', 'mathematics', 'biology', 'chemistry', 'physics', 'commerce', 'arts', 'other'],
        'diploma': ['computer science', 'information technology', 'electronics', 'electrical', 'mechanical', 'civil', 'other'],
        'b.a': ['arts', 'other'],
        'm.a': ['arts', 'other'],
        'b.com': ['commerce', 'business administration', 'mathematics', 'other'],
        'm.com': ['commerce', 'business administration', 'mathematics', 'other'],
        'b.sc': ['science', 'mathematics', 'biology', 'chemistry', 'physics', 'other'],
        'm.sc': ['science', 'mathematics', 'biology', 'chemistry', 'physics', 'other'],
        'b.tech': ['computer science', 'information technology', 'electronics', 'electrical', 'mechanical', 'civil', 'mathematics', 'physics', 'other'],
        'b.e': ['computer science', 'information technology', 'electronics', 'electrical', 'mechanical', 'civil', 'mathematics', 'physics', 'other'],
        'm.tech': ['computer science', 'information technology', 'electronics', 'electrical', 'mechanical', 'civil', 'mathematics', 'physics', 'other'],
        'm.e': ['computer science', 'information technology', 'electronics', 'electrical', 'mechanical', 'civil', 'mathematics', 'physics', 'other'],
        'bba': ['business administration', 'commerce', 'other'],
        'mba': ['business administration', 'commerce', 'other'],
        'bca': ['computer science', 'information technology', 'mathematics', 'other'],
        'mca': ['computer science', 'information technology', 'mathematics', 'other'],
        'b.ed': ['arts', 'science', 'mathematics', 'other'],
        'm.ed': ['arts', 'science', 'mathematics', 'other'],
        'llb': ['arts', 'other'],
        'llm': ['arts', 'other'],
        'mbbs': ['biology', 'chemistry', 'science', 'other'],
        'bds': ['biology', 'chemistry', 'science', 'other'],
        'md': ['biology', 'chemistry', 'science', 'other'],
        'mds': ['biology', 'chemistry', 'science', 'other'],
        'b.pharm': ['biology', 'chemistry', 'science', 'other'],
        'm.pharm': ['biology', 'chemistry', 'science', 'other'],
        'ms': ['science', 'mathematics', 'other'],
        'ca': ['commerce', 'business administration', 'mathematics', 'other'],
        'cs': ['commerce', 'business administration', 'other'],
        'icwa': ['commerce', 'business administration', 'mathematics', 'other'],
        'phd': ['science', 'arts', 'commerce', 'mathematics', 'biology', 'chemistry', 'physics', 'computer science', 'other'],
        'other': ['other'],
    }

    through = EducationSubject.educations.through
    rows = []
    for education_name, subject_names in education_subject_map.items():
        education_id = education_map.get(education_name)
        if not education_id:
            continue
        for subject_name in subject_names:
            subject_id = subject_map.get(_norm(subject_name))
            if subject_id:
                rows.append(
                    through(educationsubject_id=subject_id, education_id=education_id)
                )
    through.objects.bulk_create(rows, ignore_conflicts=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('master', '0007_employmentstatus_educationsubject_educations'),
    ]

    operations = [
        migrations.RunPython(seed_employment_and_subject_map, noop),
    ]
