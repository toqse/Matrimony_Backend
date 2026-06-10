from django.db import migrations, models
from django.utils import timezone


def _viewer_has_active_plan(UserPlan, viewer_id, today):
    try:
        up = UserPlan.objects.select_related('plan').get(user_id=viewer_id)
    except UserPlan.DoesNotExist:
        return False
    if not getattr(up, 'is_active', True):
        return False
    plan = getattr(up, 'plan', None)
    if not plan or not getattr(plan, 'is_active', True):
        return False
    if up.valid_until and up.valid_until < today:
        return False
    return True


def mark_unlocked_for_active_plan_viewers(apps, schema_editor):
    ProfileView = apps.get_model('plans', 'ProfileView')
    UserPlan = apps.get_model('plans', 'UserPlan')
    today = timezone.now().date()
    for pv in ProfileView.objects.all().only('id', 'viewer_id', 'created_at'):
        if _viewer_has_active_plan(UserPlan, pv.viewer_id, today):
            ProfileView.objects.filter(pk=pv.pk).update(
                unlocked=True,
                unlocked_at=pv.created_at,
            )


def noop_reverse(apps, schema_editor):
    ProfileView = apps.get_model('plans', 'ProfileView')
    ProfileView.objects.update(unlocked=False, unlocked_at=None)


class Migration(migrations.Migration):

    dependencies = [
        ('plans', '0019_alter_profileview_last_viewed_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='profileview',
            name='unlocked',
            field=models.BooleanField(
                default=False,
                help_text='True when the viewer spent a profile-view credit to unlock full contact/family details.',
            ),
        ),
        migrations.AddField(
            model_name='profileview',
            name='unlocked_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When this profile was first unlocked by the viewer.',
                null=True,
            ),
        ),
        migrations.RunPython(mark_unlocked_for_active_plan_viewers, noop_reverse),
    ]
