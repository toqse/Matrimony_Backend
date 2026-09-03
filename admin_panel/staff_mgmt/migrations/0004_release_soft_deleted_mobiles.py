# Generated manually for soft-deleted staff phone release

from __future__ import annotations

from django.db import migrations


def _tombstone_staff_mobile(staff_id: int) -> str:
    return f"0{staff_id:09d}"


def _tombstone_admin_mobile(staff_id: int) -> str:
    return f"+910{staff_id:09d}"


def _is_tombstone_staff_mobile(mobile: str | None) -> bool:
    if not mobile or len(mobile) != 10:
        return False
    return mobile.startswith("0") and mobile[1:].isdigit()


def release_soft_deleted_mobiles(apps, schema_editor):
    StaffProfile = apps.get_model("staff_mgmt", "StaffProfile")
    AdminUser = apps.get_model("admin_auth", "AdminUser")

    for staff in StaffProfile.objects.filter(is_deleted=True).iterator():
        if _is_tombstone_staff_mobile(staff.mobile):
            continue

        sid = staff.pk
        staff.mobile = _tombstone_staff_mobile(sid)
        staff.email = None
        staff.login_username = None
        staff.is_active = False
        staff.save(
            update_fields=[
                "mobile",
                "email",
                "login_username",
                "is_active",
            ]
        )

        try:
            admin = AdminUser.objects.get(pk=staff.admin_user_id)
        except AdminUser.DoesNotExist:
            continue
        admin.mobile = _tombstone_admin_mobile(sid)
        admin.is_active = False
        if admin.email:
            admin.email = ""
        admin.save(update_fields=["mobile", "email", "is_active"])


def noop_reverse(apps, schema_editor):
    # Original mobiles cannot be restored after tombstone.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("staff_mgmt", "0003_staffprofile_deactivated_by_branch"),
        ("admin_auth", "0002_adminuser_email"),
    ]

    operations = [
        migrations.RunPython(release_soft_deleted_mobiles, noop_reverse),
    ]
