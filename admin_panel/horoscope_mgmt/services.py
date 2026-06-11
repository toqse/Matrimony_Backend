from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce

from accounts.models import User
from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_admin_role
from admin_panel.my_profiles.views import _my_profiles_base_queryset
from admin_panel.staff_dashboard.services import staff_profile_for_dashboard
from admin_panel.subscriptions.models import CustomerStaffAssignment
from astrology.charts import format_dasa_balance, moon_rasi_name, star_name
from astrology.models import AstrologyPdfCredit, HoroscopeProfile, PoruthamResult
from astrology.porutham import calculate_porutham
from master.models import Branch as MasterBranch
from plans.models import UserPlan
from profiles.models import UserProfile


def _manager_branch_code(user) -> str | None:
    return (
        MasterBranch.objects.filter(pk=getattr(user, 'branch_id', None))
        .values_list('code', flat=True)
        .first()
    )


def scoped_member_users_queryset(request, *, mount: str):
    user = request.user
    role = normalize_admin_role(getattr(user, 'role', ''))
    base = _my_profiles_base_queryset()

    if mount == 'admin':
        if role != AdminUser.ROLE_ADMIN:
            return None
        return base

    if mount == 'staff':
        if role != AdminUser.ROLE_STAFF:
            return None
        staff = staff_profile_for_dashboard(user)
        if not staff:
            return None
        user_ids = CustomerStaffAssignment.objects.filter(
            staff=staff
        ).values_list('user_id', flat=True)
        return base.filter(id__in=user_ids)

    if mount == 'branch':
        if role != AdminUser.ROLE_BRANCH_MANAGER:
            return None
        code = _manager_branch_code(user)
        if not code:
            return base.none()
        return base.filter(
            Q(branch__code=code) | Q(staff_assignment__staff__branch__code=code)
        ).distinct()

    return None


def build_summary_counts(users_qs) -> dict[str, int]:
    total = users_qs.count()
    calculated = HoroscopeProfile.objects.filter(
        user__in=users_qs.values('pk'),
        is_calculated=True,
    ).count()
    pending = HoroscopeProfile.objects.filter(
        user__in=users_qs.values('pk'),
        is_calculated=False,
        pr_lat__isnull=False,
        pr_tob__isnull=False,
    ).count()
    match_total = (
        UserPlan.objects.filter(user__in=users_qs.values('pk'))
        .aggregate(s=Coalesce(Sum('horoscope_used'), 0))
        .get('s') or 0
    )
    return {
        'total_horoscopes': total,
        'jathagam_generated': calculated,
        'pending_generation': pending,
        'match_calculations': int(match_total),
        'mangal_dosham': 0,
    }


def panel_jathagam_pdf_path(mount: str, horoscope_id: int) -> str:
    return f'/api/v1/{mount}/horoscope/jathagam/{horoscope_id}/'


def get_horoscope_in_scope(users_qs, horoscope_id: int) -> HoroscopeProfile | None:
    return (
        HoroscopeProfile.objects.filter(id=horoscope_id, user__in=users_qs)
        .select_related('user')
        .first()
    )


def build_record_row(
    user: User,
    hp_by_user_id: dict,
    *,
    request=None,
    mount: str | None = None,
) -> dict[str, Any]:
    hp = hp_by_user_id.get(user.pk)
    profile = getattr(user, 'user_profile', None)
    rel = getattr(user, 'user_religion', None)

    # Prefer the derived fields, but fall back to values computed straight from
    # the raw EXE output (pr_star / pr_rasi). The derived star_name/rasi_sign are
    # only filled once mark_horoscope_done runs, so relying on them alone hides
    # members whose horoscope the EXE already produced.
    star_display = ''
    rasi_display = ''
    dasa_display = ''
    if hp:
        star_display = hp.star_name or star_name(hp.pr_star)
        rasi_display = hp.rasi_sign or moon_rasi_name(hp.pr_rasi)
        dasa_display = format_dasa_balance(hp.pr_dasabalance).get('balance_text', '')

    # PDF generation requires the full 11-char pr_rasi chart (same check as
    # JathagamPDFView). Star-only legacy imports must not show Ready/PDF.
    has_chart = bool(hp and hp.pr_rasi and len(hp.pr_rasi) >= 11)
    is_ready = has_chart
    jathagam = 'calculated' if has_chart else 'awaiting_exe'
    pdf_url = None
    if is_ready and hp and request and mount:
        pdf_url = request.build_absolute_uri(panel_jathagam_pdf_path(mount, hp.pk))

    return {
        'profile_id': profile.pk if profile else None,
        'user_id': str(user.pk),
        'horoscope_id': hp.pk if hp else None,
        'matri_id': user.matri_id or '',
        'name': (user.name or '').strip(),
        'branch': user.branch.name if user.branch_id else '',
        'religion': rel.religion.name if rel and rel.religion_id else '',
        'dob': user.dob.isoformat() if user.dob else None,
        'rasi': rasi_display,
        'nakshatram': star_display,
        'star_display': star_display,
        'dasa_display': dasa_display,
        'pr_rasi': hp.pr_rasi if hp else '',
        'pr_star': hp.pr_star if hp else None,
        'pr_pada': hp.pr_pada if hp else None,
        'dosham': '',
        'mangal': None,
        'jathagam': jathagam,
        'is_ready': is_ready,
        'pdf_url': pdf_url,
        'last_edited_at': profile.updated_at.isoformat() if profile else None,
    }


def _list_users_filtered(users_qs, *, search: str, branch_id: str | None):
    qs = users_qs
    if branch_id:
        try:
            qs = qs.filter(branch_id=int(branch_id))
        except (TypeError, ValueError):
            pass
    s = (search or '').strip()
    if s:
        qs = qs.filter(Q(matri_id__icontains=s) | Q(name__icontains=s))
    return qs.order_by('-created_at')


def paginate(qs, page: int, page_size: int):
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    total = qs.count()
    start = (page - 1) * page_size
    return total, qs[start: start + page_size]


def list_horoscope_records(
    users_qs,
    *,
    search,
    branch_id,
    page,
    page_size,
    request=None,
    mount: str | None = None,
):
    qs = _list_users_filtered(users_qs, search=search, branch_id=branch_id)
    total, page_qs = paginate(qs, page, page_size)
    user_ids = [u.pk for u in page_qs]
    hp_map = {
        h.user_id: h
        for h in HoroscopeProfile.objects.filter(user_id__in=user_ids)
    }

    page = max(1, int(page))
    page_size = max(1, min(100, int(page_size)))
    end = page * page_size
    next_link = (
        f'?page={page + 1}&page_size={page_size}' if end < total else None
    )
    previous_link = (
        f'?page={page - 1}&page_size={page_size}' if page > 1 else None
    )

    return {
        'count': total,
        'page': page,
        'page_size': page_size,
        'next': next_link,
        'previous': previous_link,
        'results': [
            build_record_row(u, hp_map, request=request, mount=mount) for u in page_qs
        ],
    }


def user_in_scope(users_qs, user_id: UUID) -> bool:
    return users_qs.filter(pk=user_id).exists()


def get_target_user_in_scope(users_qs, user_id: UUID) -> User | None:
    return users_qs.filter(pk=user_id).first()


def get_target_user_by_matri(users_qs, matri_id: str) -> User | None:
    mid = (matri_id or '').strip()
    if not mid:
        return None
    return users_qs.filter(matri_id__iexact=mid).first()


def record_detail(
    users_qs,
    user_id: UUID,
    *,
    request=None,
    mount: str | None = None,
) -> dict[str, Any] | None:
    from astrology.serializers import HoroscopeProfileSerializer

    user = get_target_user_in_scope(users_qs, user_id)
    if not user:
        return None
    hp = HoroscopeProfile.objects.filter(user=user).first()
    return {
        'record': build_record_row(
            user,
            {user.pk: hp} if hp else {},
            request=request,
            mount=mount,
        ),
        'horoscope': HoroscopeProfileSerializer(hp).data if hp else None,
    }


def run_mark_horoscope_done(users_qs) -> dict[str, int]:
    """
    Fill derived fields for in-scope profiles where EXE wrote pr_rasi but
    is_calculated is still False.
    """
    from astrology.management.commands.mark_horoscope_done import fill_derived

    user_ids = users_qs.values_list('pk', flat=True)
    qs = HoroscopeProfile.objects.filter(
        user_id__in=user_ids,
        is_calculated=False,
        pr_rasi__isnull=False,
    ).exclude(pr_rasi='')

    processed = 0
    errors = 0
    for hp in qs.iterator(chunk_size=100):
        try:
            if not hp.pr_rasi or len(hp.pr_rasi) < 3:
                continue
            fill_derived(hp)
            UserProfile.objects.filter(user_id=hp.user_id).update(has_horoscope=True)
            processed += 1
        except Exception:
            errors += 1

    return {'processed': processed, 'errors': errors}


def record_detail_by_matri(
    users_qs,
    matri_id: str,
    *,
    request=None,
    mount: str | None = None,
) -> dict[str, Any] | None:
    user = get_target_user_by_matri(users_qs, matri_id)
    if not user:
        return None
    return record_detail(users_qs, user.pk, request=request, mount=mount)


def panel_porutham(
    users_qs,
    bride_profile_id: int,
    groom_profile_id: int,
    *,
    request=None,
    chart_style: str = 'south',
) -> tuple[dict | None, str | None]:
    from astrology.serializers import HoroscopeProfileSerializer

    b_prof = UserProfile.objects.filter(
        pk=bride_profile_id
    ).select_related('user').first()
    g_prof = UserProfile.objects.filter(
        pk=groom_profile_id
    ).select_related('user').first()

    if not b_prof or not g_prof:
        return None, 'Invalid profile id(s).'
    if not user_in_scope(users_qs, b_prof.user_id) or not user_in_scope(
        users_qs, g_prof.user_id
    ):
        return None, 'One or both profiles are out of scope.'

    try:
        bride_hp = b_prof.user.horoscope_profile
        groom_hp = g_prof.user.horoscope_profile
    except HoroscopeProfile.DoesNotExist:
        return None, 'Horoscope not found. Run Windows EXE first.'

    if not bride_hp.is_exe_done() or not groom_hp.is_exe_done():
        return None, 'EXE has not written horoscope results yet.'

    porutham = calculate_porutham(bride_hp, groom_hp)

    return {
        'bride_horoscope': HoroscopeProfileSerializer(bride_hp).data,
        'groom_horoscope': HoroscopeProfileSerializer(groom_hp).data,
        **porutham,
    }, None


def list_jathakam_pdf_credits(users_qs):
    user_ids = users_qs.values_list('pk', flat=True)
    qs = (
        AstrologyPdfCredit.objects.filter(
            user_id__in=user_ids,
            product=AstrologyPdfCredit.PRODUCT_JATHAKAM,
        )
        .select_related('user')
        .order_by('-created_at')[:500]
    )
    return [
        {
            'credit_id': c.pk,
            'matri_id': getattr(c.user, 'matri_id', '') or '',
            'name': (getattr(c.user, 'name', '') or '').strip(),
            'consumed_at': c.consumed_at.isoformat() if c.consumed_at else None,
            'created_at': c.created_at.isoformat(),
        }
        for c in qs
    ]
