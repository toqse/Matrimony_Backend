# Generated manually: ProfileView now references profiles.UserProfile.

import django.db.models.deletion
from django.db import migrations, models


def forwards_profile_fk(apps, schema_editor):
    ProfileView = apps.get_model("plans", "ProfileView")
    UserProfile = apps.get_model("profiles", "UserProfile")
    for pv in ProfileView.objects.all().only("id", "viewed_user_id", "profile_id"):
        if pv.profile_id:
            continue
        up = UserProfile.objects.filter(user_id=pv.viewed_user_id).first()
        if up:
            ProfileView.objects.filter(pk=pv.pk).update(profile_id=up.pk)
        else:
            ProfileView.objects.filter(pk=pv.pk).delete()


def dedupe_by_viewer_profile(apps, schema_editor):
    ProfileView = apps.get_model("plans", "ProfileView")
    seen = set()
    to_delete = []
    for row in ProfileView.objects.order_by("id"):
        key = (row.viewer_id, row.profile_id)
        if key in seen:
            to_delete.append(row.pk)
        else:
            seen.add(key)
    if to_delete:
        ProfileView.objects.filter(pk__in=to_delete).delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("plans", "0015_remove_transaction_plans_txn_type_created_desc"),
        ("profiles", "0013_replace_partner_caste_preference"),
    ]

    operations = [
        migrations.AddField(
            model_name="profileview",
            name="profile",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="profile_views",
                to="profiles.userprofile",
            ),
        ),
        migrations.RunPython(forwards_profile_fk, noop),
        migrations.RunPython(dedupe_by_viewer_profile, noop),
        migrations.RemoveConstraint(
            model_name="profileview",
            name="uniq_profile_view_pair",
        ),
        migrations.RemoveIndex(
            model_name="profileview",
            name="plans_profi_viewer__b69bb8_idx",
        ),
        migrations.RemoveIndex(
            model_name="profileview",
            name="plans_profi_viewer__36fd6d_idx",
        ),
        migrations.RemoveField(
            model_name="profileview",
            name="viewed_user",
        ),
        migrations.RemoveField(
            model_name="profileview",
            name="timestamp",
        ),
        migrations.RemoveField(
            model_name="profileview",
            name="updated_at",
        ),
        migrations.AlterField(
            model_name="profileview",
            name="profile",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="profile_views",
                to="profiles.userprofile",
            ),
        ),
        migrations.AddConstraint(
            model_name="profileview",
            constraint=models.UniqueConstraint(
                fields=("viewer", "profile"),
                name="uniq_profile_view_pair",
            ),
        ),
        migrations.AddIndex(
            model_name="profileview",
            index=models.Index(
                fields=["viewer", "profile"],
                name="plans_profi_viewer_pr_f6a1_idx",
            ),
        ),
    ]
