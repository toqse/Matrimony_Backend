"""
Merge two user accounts (duplicate matri_ids) into one primary account.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

if TYPE_CHECKING:
    from accounts.models import User


def _ordered_user_pair(a, b):
    """Conversation constraint: user1_id < user2_id (string compare UUIDs)."""
    sa, sb = str(a.pk), str(b.pk)
    return (a, b) if sa < sb else (b, a)


def merge_user_accounts(primary: "User", duplicate: "User") -> None:
    """
    Reassign all references from duplicate -> primary, then retire duplicate user row.
    Does not delete primary data; moves duplicate-only rows where primary has none.
    """
    from admin_panel.commissions.models import Commission
    from admin_panel.subscriptions.models import CustomerStaffAssignment
    from notifications.models import NotificationLog
    from plans.models import Conversation, Interest, Message, ProfileView, Transaction, UserPlan
    from profiles.models import (
        UserEducation,
        UserFamily,
        UserLocation,
        UserPersonal,
        UserPhotos,
        UserProfile,
        UserReligion,
    )
    from user_settings.models import UserSettings as UserSettingsModel
    from wishlist.models import Wishlist

    assert primary.pk != duplicate.pk

    with transaction.atomic():
        # --- OneToOne: UserPlan ---
        dup_plan = UserPlan.objects.filter(user=duplicate).first()
        pri_plan = UserPlan.objects.filter(user=primary).first()
        if dup_plan and not pri_plan:
            UserPlan.objects.filter(pk=dup_plan.pk).update(user=primary)
        elif dup_plan and pri_plan:
            Transaction.objects.filter(user=duplicate).update(user=primary)
            dup_plan.delete()

        # --- FK lists ---
        Transaction.objects.filter(user=duplicate).update(user=primary)
        Commission.objects.filter(customer=duplicate).update(customer=primary)

        dup_asgn = CustomerStaffAssignment.objects.filter(user=duplicate).first()
        pri_asgn = CustomerStaffAssignment.objects.filter(user=primary).first()
        if dup_asgn:
            if pri_asgn:
                dup_asgn.delete()
            else:
                CustomerStaffAssignment.objects.filter(pk=dup_asgn.pk).update(user=primary)

        Interest.objects.filter(sender=duplicate).update(sender=primary)
        Interest.objects.filter(receiver=duplicate).update(receiver=primary)
        Interest.objects.filter(sender=primary, receiver=primary).delete()
        _dedupe_interests(primary)

        primary_prof = UserProfile.objects.filter(user=primary).first()
        duplicate_prof = UserProfile.objects.filter(user=duplicate).first()
        if primary_prof and duplicate_prof:
            ProfileView.objects.filter(profile=duplicate_prof).update(profile=primary_prof)
        ProfileView.objects.filter(viewer=duplicate).update(viewer=primary)
        ProfileView.objects.filter(viewer=primary, profile__user=primary).delete()
        _dedupe_profile_views(primary)

        Wishlist.objects.filter(user=duplicate).update(user=primary)
        Wishlist.objects.filter(profile=duplicate).update(profile=primary)
        _dedupe_wishlist(primary)

        NotificationLog.objects.filter(user=duplicate).update(user=primary)

        dup_set = UserSettingsModel.objects.filter(user=duplicate).first()
        pri_set = UserSettingsModel.objects.filter(user=primary).first()
        if dup_set and not pri_set:
            UserSettingsModel.objects.filter(pk=dup_set.pk).update(user=primary)
        elif dup_set and pri_set:
            dup_set.delete()

        Message.objects.filter(sender=duplicate).update(sender=primary)

        _merge_conversations(primary, duplicate)

        # --- Profile OneToOne ---
        _move_o2o(UserProfile, primary, duplicate)
        _move_o2o(UserLocation, primary, duplicate)
        _move_o2o(UserReligion, primary, duplicate)
        _move_o2o(UserPersonal, primary, duplicate)
        _move_o2o(UserFamily, primary, duplicate)
        _move_o2o(UserEducation, primary, duplicate)
        _move_o2o(UserPhotos, primary, duplicate)

        # --- Retire duplicate user ---
        old_matri = duplicate.matri_id or ""
        suffix = uuid.uuid4().hex[:6].upper()
        new_matri = (f"{old_matri}_M{suffix}")[:20]
        if len(new_matri) < 8:
            new_matri = f"ZRET_{suffix}"

        anon_mobile = f"X{str(duplicate.pk).replace('-', '')[:15]}"
        if len(anon_mobile) > 20:
            anon_mobile = anon_mobile[:20]

        duplicate.matri_id = new_matri
        duplicate.mobile = anon_mobile if duplicate.mobile else None
        duplicate.email = None
        duplicate.is_active = False
        duplicate.save(update_fields=["matri_id", "mobile", "email", "is_active", "updated_at"])


def _dedupe_interests(primary):
    from plans.models import Interest

    seen = set()
    for row in Interest.objects.filter(Q(sender=primary) | Q(receiver=primary)).order_by("id"):
        key = (row.sender_id, row.receiver_id)
        if key in seen:
            row.delete()
        else:
            seen.add(key)


def _dedupe_profile_views(primary):
    from plans.models import ProfileView

    seen = set()
    for row in ProfileView.objects.filter(Q(viewer=primary) | Q(profile__user=primary)).order_by("id"):
        key = (row.viewer_id, row.profile_id)
        if key in seen:
            row.delete()
        else:
            seen.add(key)


def _dedupe_wishlist(primary):
    from wishlist.models import Wishlist

    seen = set()
    for row in Wishlist.objects.filter(Q(user=primary) | Q(profile=primary)).order_by("id"):
        key = (row.user_id, row.profile_id)
        if key in seen:
            row.delete()
        else:
            seen.add(key)


def _merge_conversations(primary, duplicate):
    from plans.models import Conversation

    for c in list(Conversation.objects.filter(Q(user1=duplicate) | Q(user2=duplicate))):
        u1 = primary if c.user1_id == duplicate.pk else c.user1
        u2 = primary if c.user2_id == duplicate.pk else c.user2
        if u1.pk == u2.pk:
            c.delete()
            continue
        u1, u2 = _ordered_user_pair(u1, u2)
        if Conversation.objects.filter(user1=u1, user2=u2).exclude(pk=c.pk).exists():
            c.delete()
        else:
            Conversation.objects.filter(pk=c.pk).update(
                user1=u1,
                user2=u2,
                updated_at=timezone.now(),
            )


def _move_o2o(model, primary: "User", duplicate: "User"):
    dup_row = model.objects.filter(user=duplicate).first()
    if not dup_row:
        return
    pri_row = model.objects.filter(user=primary).first()
    if pri_row:
        dup_row.delete()
    else:
        model.objects.filter(pk=dup_row.pk).update(user=primary)
