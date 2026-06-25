"""Reference-profile porutham filters for admin / branch / staff profile lists."""
from __future__ import annotations

from accounts.models import User
from astrology.models import HoroscopeProfile
from astrology.porutham import UTHAMAM, calculate_porutham

from .profile_filters import _qp

PORUTHAM_CANDIDATE_CAP = 500

TOO_MANY_CANDIDATES_MSG = (
    "Too many profiles match your filters for horoscope matching. "
    "Please narrow the search (religion, caste, state, age, etc.) and try again."
)
REFERENCE_NOT_FOUND_MSG = "Reference profile not found."
REFERENCE_HOROSCOPE_MSG = (
    "Reference profile horoscope is not calculated yet. "
    "Generate horoscope for the reference member first."
)
INVALID_GENDER_PAIR_MSG = (
    "Reference and candidate must be opposite genders (M/F) for porutham matching."
)


def porutham_filter_requested(request) -> bool:
    return bool(_qp(request, "match_matri_id"))


def _horoscope_ready(hp: HoroscopeProfile | None) -> bool:
    return bool(hp and hp.pr_rasi and len(hp.pr_rasi) >= 11)


def _bride_groom_hps(
    ref_user: User,
    ref_hp: HoroscopeProfile,
    cand_user: User,
    cand_hp: HoroscopeProfile,
) -> tuple[HoroscopeProfile, HoroscopeProfile] | tuple[None, None]:
    ref_g = (ref_user.gender or "").upper()
    cand_g = (cand_user.gender or "").upper()
    if ref_g == "F" and cand_g == "M":
        return ref_hp, cand_hp
    if ref_g == "M" and cand_g == "F":
        return cand_hp, ref_hp
    return None, None


def _passes_porutham_filters(result: dict, request) -> bool:
    min_raw = _qp(request, "min_porutham_count")
    if min_raw.isdigit():
        if int(result.get("total_porutham_count") or 0) < int(min_raw):
            return False

    rajju_match = _qp(request, "rajju_match").lower()
    rajju_grade = result.get("rajju_dosham")
    if rajju_match == "pass" and rajju_grade != UTHAMAM:
        return False
    if rajju_match == "fail" and rajju_grade == UTHAMAM:
        return False

    horoscope_match = _qp(request, "horoscope_match").lower()
    if horoscope_match == "good":
        if result.get("overall_result") not in {"Good", "Excellent"}:
            return False

    star_match = _qp(request, "star_match").lower()
    if star_match == "yes":
        poruthams = result.get("poruthams") or {}
        if not (poruthams.get("dinam") and poruthams.get("ganam")):
            return False

    return True


def apply_porutham_match_filters(qs, request):
    """
    When match_matri_id is set, keep only candidates compatible with the reference.
    Returns (queryset, error_message).
    """
    match_matri_id = _qp(request, "match_matri_id")
    if not match_matri_id:
        return qs, None

    ref_user = User.objects.filter(matri_id__iexact=match_matri_id, role="user").first()
    if not ref_user:
        return None, REFERENCE_NOT_FOUND_MSG

    try:
        ref_hp = HoroscopeProfile.objects.get(user_id=ref_user.pk)
    except HoroscopeProfile.DoesNotExist:
        return None, REFERENCE_HOROSCOPE_MSG

    if not _horoscope_ready(ref_hp):
        return None, REFERENCE_HOROSCOPE_MSG

    candidate_ids = list(qs.exclude(pk=ref_user.pk).values_list("pk", flat=True)[: PORUTHAM_CANDIDATE_CAP + 1])
    if len(candidate_ids) > PORUTHAM_CANDIDATE_CAP:
        return None, TOO_MANY_CANDIDATES_MSG

    candidates = {
        u.pk: u
        for u in User.objects.filter(pk__in=candidate_ids).only("pk", "gender")
    }
    horoscopes = {
        hp.user_id: hp
        for hp in HoroscopeProfile.objects.filter(user_id__in=candidate_ids)
    }

    matching_ids: list = []
    for pk in candidate_ids:
        cand_user = candidates.get(pk)
        cand_hp = horoscopes.get(pk)
        if not cand_user or not _horoscope_ready(cand_hp):
            continue
        pair = _bride_groom_hps(ref_user, ref_hp, cand_user, cand_hp)
        if not pair:
            continue
        bride_hp, groom_hp = pair
        result = calculate_porutham(bride_hp, groom_hp)
        if _passes_porutham_filters(result, request):
            matching_ids.append(pk)

    return qs.filter(pk__in=matching_ids), None
