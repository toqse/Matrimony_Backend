"""
Link admin_panel.branches.Branch to master.Branch by code.

AdminUser.branch FK points to master.Branch; staff profiles use admin branch rows.
When master data was missing, logins were created with branch=NULL — this fixes that at create time and for backfill.
"""

from __future__ import annotations

from master.models import Branch as MasterBranch


def ensure_master_branch_from_admin_branch(admin_branch) -> MasterBranch | None:
    """
    Return master.Branch for this admin branch, creating it if missing (same code + name).
    """
    if not admin_branch:
        return None
    code = (admin_branch.code or "").strip()
    if not code:
        return None
    name = (admin_branch.name or code).strip() or code
    is_active = bool(getattr(admin_branch, "is_active", True))
    mb, created = MasterBranch.objects.get_or_create(
        code=code,
        defaults={"name": name, "is_active": is_active},
    )
    if not created:
        updates = []
        if mb.name != name:
            mb.name = name
            updates.append("name")
        if not mb.is_active and is_active:
            mb.is_active = True
            updates.append("is_active")
        if updates:
            mb.save(update_fields=updates)
    return mb
