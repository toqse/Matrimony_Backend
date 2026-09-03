"""Helpers to soft-delete staff and free unique contact/login fields."""

from __future__ import annotations

from admin_panel.staff_mgmt.models import StaffProfile


def tombstone_staff_mobile(staff_id: int) -> str:
    """10-digit non-real mobile unique by staff id (Indian numbers never start with 0)."""
    return f"0{staff_id:09d}"


def tombstone_admin_mobile(staff_id: int) -> str:
    """E.164-style tombstone fitting AdminUser.mobile max_length=15."""
    return f"+910{staff_id:09d}"


def is_tombstone_staff_mobile(mobile: str | None) -> bool:
    if not mobile or len(mobile) != 10:
        return False
    return mobile.startswith("0") and mobile[1:].isdigit()


def release_staff_unique_fields(staff: StaffProfile, *, save: bool = True) -> StaffProfile:
    """
    Free mobile / email / login_username so they can be reused by a new staff member.

    Marks the profile inactive + deleted and disables the linked AdminUser login.
    """
    sid = staff.pk
    staff.mobile = tombstone_staff_mobile(sid)
    if staff.email:
        # EmailField unique allows one NULL; clear rather than invent a fake address.
        staff.email = None
    if staff.login_username:
        staff.login_username = None
    staff.is_active = False
    staff.is_deleted = True

    admin = staff.admin_user
    admin.mobile = tombstone_admin_mobile(sid)
    admin.is_active = False
    if admin.email:
        admin.email = ""

    if save:
        staff.save(
            update_fields=[
                "mobile",
                "email",
                "login_username",
                "is_active",
                "is_deleted",
                "updated_at",
            ]
        )
        admin.save(update_fields=["mobile", "email", "is_active", "updated_at"])

    return staff
