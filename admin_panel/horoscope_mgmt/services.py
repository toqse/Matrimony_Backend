"""
Horoscope management panel: scoped querysets, KPI summary, list rows, porutham (no quota).

Birth/chart refresh uses astrology.services.horoscope_runtime (same as member APIs).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db.models import Exists, OuterRef, Q, Sum
from django.db.models.functions import Coalesce

from accounts.models import User
from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_admin_role
from admin_panel.my_profiles.views import _my_profiles_base_queryset
from admin_panel.staff_dashboard.services import staff_profile_for_dashboard
from admin_panel.subscriptions.models import CustomerStaffAssignment
from astrology.models import AstrologyPdfCredit, Horoscope
from astrology.services.generate_ui_service import kuja_dosham_horoscope
from astrology.services.horoscope_runtime import create_or_update_horoscope
from astrology.services.porutham_service import calculate_porutham
from master.models import Branch as MasterBranch
from plans.models import UserPlan
from profiles.models import UserProfile


def _manager_branch_code(user) -> str | None:
    return (
        MasterBranch.objects.filter(pk=getattr(user, "branch_id", None))
        .values_list("code", flat=True)
        .first()
    )


def scoped_member_users_queryset(request, *, mount: str):
    """
    mount: 'admin' | 'staff' | 'branch'
    Returns queryset of User (role=user, active) or None if caller should return 403/400.
    """
    user = request.user
    role = normalize_admin_role(getattr(user, "role", ""))

    base = _my_profiles_base_queryset()

    if mount == "admin":
        if role != AdminUser.ROLE_ADMIN:
            return None
        return base

    if mount == "staff":
        if role != AdminUser.ROLE_STAFF:
            return None
        staff = staff_profile_for_dashboard(user)
        if not staff:
            return None
        user_ids = CustomerStaffAssignment.objects.filter(staff=staff).values_list("user_id", flat=True)
        return base.filter(id__in=user_ids)

    if mount == "branch":
        if role != AdminUser.ROLE_BRANCH_MANAGER:
            return None
        code = _manager_branch_code(user)
        if not code:
            return base.none()
        return base.filter(Q(branch__code=code) | Q(staff_assignment__staff__branch__code=code)).distinct()

    return None


def _horoscope_relevance_q():
    """Profiles counted in Total Horoscopes KPI (see module docstring in views)."""
    has_row = Exists(Horoscope.objects.filter(profile__user_id=OuterRef("pk")))
    return Q(dob__isnull=False) | Q(user_profile__has_horoscope=True) | has_row


def _birth_complete_q():
    return (
        Q(dob__isnull=False)
        & Q(user_profile__time_of_birth__isnull=False)
        & ~Q(user_profile__place_of_birth="")
    )


def build_summary_counts(users_qs) -> dict[str, int]:
    """
    KPIs for horoscope dashboard.
    total_horoscopes: member has DOB, or admin marked has_horoscope, or computed Horoscope row exists.
    """
    rel = users_qs.filter(_horoscope_relevance_q())
    total_horoscopes = rel.count()

    jathagam_generated = rel.filter(user_profile__has_horoscope=True).count()
    pending_generation = rel.filter(_birth_complete_q(), user_profile__has_horoscope=False).count()

    mangal_dosham = 0
    profile_ids_with_h = Horoscope.objects.filter(profile__user__in=users_qs.values("pk")).select_related(
        "profile__user"
    )
    for h in profile_ids_with_h.iterator(chunk_size=500):
        if kuja_dosham_horoscope(h):
            mangal_dosham += 1

    match_total = (
        UserPlan.objects.filter(user__in=users_qs.values("pk"))
        .aggregate(s=Coalesce(Sum("horoscope_used"), 0))
        .get("s")
        or 0
    )

    return {
        "total_horoscopes": total_horoscopes,
        "jathagam_generated": jathagam_generated,
        "pending_generation": pending_generation,
        "match_calculations": int(match_total),
        "mangal_dosham": mangal_dosham,
    }


def _jathagam_status(user: User, profile: UserProfile | None, has_horoscope_row: bool) -> str:
    if profile and profile.has_horoscope:
        return "generated"
    if profile and user.dob and profile.time_of_birth and (profile.place_of_birth or "").strip():
        return "pending"
    return "na"


def _dosham_label(profile: UserProfile | None, horoscope: Horoscope | None) -> str:
    if profile and profile.horoscope_data:
        d = (profile.horoscope_data.get("dosham") or "").strip()
        if d:
            return d
    if horoscope:
        parts = []
        if horoscope.rajju:
            parts.append(f"Rajju: {horoscope.rajju}")
        if kuja_dosham_horoscope(horoscope):
            parts.append("Kuja dosham")
        return "; ".join(parts) if parts else "No Dosham"
    return ""


def _list_users_filtered(users_qs, *, search: str, branch_id: str | None):
    qs = users_qs
    if branch_id:
        try:
            bid = int(branch_id)
        except (TypeError, ValueError):
            bid = None
        if bid is not None:
            qs = qs.filter(branch_id=bid)
    s = (search or "").strip()
    if s:
        qs = qs.filter(Q(matri_id__icontains=s) | Q(name__icontains=s))
    return qs.order_by("-created_at")


def paginate(qs, page: int, page_size: int):
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    total = qs.count()
    start = (page - 1) * page_size
    return total, qs[start : start + page_size]


def build_record_row(user: User, horoscope_by_profile_id: dict[int, Horoscope]) -> dict[str, Any]:
    profile = getattr(user, "user_profile", None)
    pid = profile.pk if profile else None
    h = horoscope_by_profile_id.get(pid) if pid else None

    rel = getattr(user, "user_religion", None)
    religion_name = rel.religion.name if rel and rel.religion_id else ""

    rasi = ""
    nakshatra = ""
    if h:
        rasi = h.rasi or ""
        nakshatra = h.nakshatra or ""
    elif profile and profile.horoscope_data:
        rasi = (profile.horoscope_data.get("rasi") or "").strip()
        nakshatra = (profile.horoscope_data.get("nakshatra") or "").strip()

    mangal = None
    if h is not None:
        mangal = kuja_dosham_horoscope(h)

    branch_name = user.branch.name if user.branch_id else ""

    return {
        "profile_id": pid,
        "user_id": str(user.pk),
        "matri_id": user.matri_id or "",
        "name": (user.name or "").strip(),
        "branch": branch_name,
        "religion": religion_name,
        "dob": user.dob.isoformat() if user.dob else None,
        "rasi": rasi,
        "nakshatram": nakshatra,
        "dosham": _dosham_label(profile, h),
        "mangal": mangal,
        "jathagam": _jathagam_status(user, profile, h is not None),
        "last_edited_at": profile.updated_at.isoformat() if profile else None,
    }


def list_horoscope_records(users_qs, *, search: str, branch_id: str | None, page: int, page_size: int):
    qs = _list_users_filtered(users_qs, search=search, branch_id=branch_id)
    total, page_users = paginate(qs, page, page_size)
    profile_ids = [u.user_profile.pk for u in page_users if getattr(u, "user_profile", None)]
    horo_map = {
        h.profile_id: h
        for h in Horoscope.objects.filter(profile_id__in=profile_ids).select_related("profile__user")
    }
    rows = [build_record_row(u, horo_map) for u in page_users]
    return {"count": total, "page": page, "page_size": page_size, "results": rows}


def user_in_scope(users_qs, user_id: UUID) -> bool:
    return users_qs.filter(pk=user_id).exists()


def get_target_user_in_scope(users_qs, user_id: UUID) -> User | None:
    return users_qs.filter(pk=user_id).first()


def get_target_user_by_matri(users_qs, matri_id: str) -> User | None:
    mid = (matri_id or "").strip()
    if not mid:
        return None
    return users_qs.filter(matri_id__iexact=mid).first()


def record_detail(users_qs, user_id: UUID) -> dict[str, Any] | None:
    user = get_target_user_in_scope(users_qs, user_id)
    if not user:
        return None
    profile = getattr(user, "user_profile", None)
    if not profile:
        return {"record": build_record_row(user, {}), "horoscope": None}
    h = Horoscope.objects.filter(profile=profile).first()
    horo_map = {h.profile_id: h} if h else {}
    record = build_record_row(user, horo_map)
    horoscope_payload = None
    if h:
        from astrology.serializers import HoroscopeSerializer

        horoscope_payload = HoroscopeSerializer(h).data
    return {"record": record, "horoscope": horoscope_payload}


def record_detail_by_matri(users_qs, matri_id: str) -> dict[str, Any] | None:
    user = get_target_user_by_matri(users_qs, matri_id)
    if not user:
        return None
    return record_detail(users_qs, user.pk)


def regenerate_horoscope(users_qs, user_id: UUID) -> tuple[dict[str, Any] | None, str | None]:
    """
    Returns (data, error_message). error_message set on failure.
    """
    user = get_target_user_in_scope(users_qs, user_id)
    if not user:
        return None, "Profile not found or out of scope."
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={})
    profile = UserProfile.objects.select_related("user").get(pk=profile.pk)
    try:
        h = create_or_update_horoscope(profile)
    except ValueError as e:
        return None, str(e)
    from astrology.serializers import HoroscopeSerializer

    return {"horoscope": HoroscopeSerializer(h).data}, None


def panel_porutham(users_qs, bride_profile_id: int, groom_profile_id: int) -> tuple[dict | None, str | None]:
    b_prof = UserProfile.objects.filter(pk=bride_profile_id).select_related("user").first()
    g_prof = UserProfile.objects.filter(pk=groom_profile_id).select_related("user").first()
    if not b_prof or not g_prof:
        return None, "Invalid profile id(s)."
    if not user_in_scope(users_qs, b_prof.user_id) or not user_in_scope(users_qs, g_prof.user_id):
        return None, "One or both profiles are out of scope."
    bride = Horoscope.objects.filter(profile_id=bride_profile_id).first()
    groom = Horoscope.objects.filter(profile_id=groom_profile_id).first()
    if not bride or not groom:
        return None, "Bride or groom horoscope not found. Regenerate birth charts first."
    result = calculate_porutham(bride, groom)
    return result, None


def list_jathakam_pdf_credits(users_qs):
    user_ids = users_qs.values_list("pk", flat=True)
    qs = (
        AstrologyPdfCredit.objects.filter(user_id__in=user_ids, product=AstrologyPdfCredit.PRODUCT_JATHAKAM)
        .select_related("user")
        .order_by("-created_at")[:500]
    )
    out = []
    for c in qs:
        u = c.user
        out.append(
            {
                "credit_id": c.pk,
                "matri_id": getattr(u, "matri_id", "") or "",
                "name": (getattr(u, "name", "") or "").strip(),
                "consumed_at": c.consumed_at.isoformat() if c.consumed_at else None,
                "created_at": c.created_at.isoformat(),
            }
        )
    return out
