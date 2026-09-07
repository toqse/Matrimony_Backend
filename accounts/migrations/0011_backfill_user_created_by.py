from django.db import migrations


def backfill_created_by(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    AuditLog = apps.get_model("audit_log", "AuditLog")
    StaffProfile = apps.get_model("staff_mgmt", "StaffProfile")

    source_by_role = {
        "staff": "staff",
        "admin": "admin",
        "branch_manager": "branch_manager",
    }
    staff_pk_by_admin = dict(StaffProfile.objects.values_list("admin_user_id", "pk"))

    seen_matri_ids = set()
    to_update = []
    logs = (
        AuditLog.objects.filter(action="create_profile", resource__startswith="profile:")
        .order_by("created_at")
        .values("resource", "role", "actor_id")
    )
    pending = []
    for log in logs:
        resource = log["resource"] or ""
        matri_id = resource.split(":", 1)[-1].strip() if ":" in resource else ""
        if not matri_id or matri_id in seen_matri_ids:
            continue
        source = source_by_role.get((log["role"] or "").strip())
        if not source:
            continue
        seen_matri_ids.add(matri_id)
        staff_id = None
        if source in ("staff", "branch_manager") and log["actor_id"]:
            staff_id = staff_pk_by_admin.get(log["actor_id"])
        pending.append((matri_id, source, staff_id))

    if pending:
        users_by_matri = {
            u.matri_id: u
            for u in User.objects.filter(
                role="user",
                matri_id__in=[m for m, _, _ in pending],
            )
        }
        for matri_id, source, staff_id in pending:
            user = users_by_matri.get(matri_id)
            if not user:
                continue
            user.created_source = source
            user.created_by_staff_id = staff_id
            to_update.append(user)
        if to_update:
            User.objects.bulk_update(to_update, ["created_source", "created_by_staff"])

    User.objects.filter(role="user", created_source="website").exclude(reg_no="").update(
        created_source="bulk"
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_user_created_source"),
        ("audit_log", "0007_auditlog_login_logout_actions"),
    ]

    operations = [
        migrations.RunPython(backfill_created_by, noop_reverse),
    ]
