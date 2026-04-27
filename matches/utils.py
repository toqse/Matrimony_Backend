"""
Match list: age from dob, height value, match percentage.
"""
from datetime import date, timedelta
from django.db.models import Q, Value, IntegerField, Case, When

from core.dob_utils import calculate_age
from profiles.models import UserReligion, UserEducation, UserLocation


def age_from_dob(dob):
    if not dob:
        return None
    return calculate_age(dob)


def dob_range_for_age(age_min, age_max):
    """Return (dob_min, dob_max) for filtering: age_min <= age <= age_max."""
    today = date.today()
    # age_max=30 -> dob_min = 30 years ago (youngest)
    # age_min=25 -> dob_max = 25 years ago (oldest)
    from datetime import timedelta
    dob_max = today - timedelta(days=365 * age_min) if age_min is not None else None
    dob_min = today - timedelta(days=365 * (age_max + 1)) if age_max is not None else None
    return dob_min, dob_max


def compute_match_percentage(viewer, profile_user, viewer_rel, viewer_pers, viewer_edu, viewer_loc,
                             profile_rel, profile_pers, profile_edu, profile_loc):
    """
    Simple match score 0-100 using religion, education, location, age, occupation.
    viewer_* and profile_* are the related objects (UserReligion, UserPersonal, UserEducation, UserLocation).
    """
    score = 0
    # Religion match (20)
    if viewer_rel and profile_rel and viewer_rel.religion_id and profile_rel.religion_id:
        if viewer_rel.religion_id == profile_rel.religion_id:
            score += 20
    # Education (15)
    if viewer_edu and profile_edu and viewer_edu.highest_education_id and profile_edu.highest_education_id:
        if viewer_edu.highest_education_id == profile_edu.highest_education_id:
            score += 15
    # Location / state (15)
    if viewer_loc and profile_loc and viewer_loc.state_id and profile_loc.state_id:
        if viewer_loc.state_id == profile_loc.state_id:
            score += 15
    # Occupation (10)
    if viewer_edu and profile_edu and viewer_edu.occupation_id and profile_edu.occupation_id:
        if viewer_edu.occupation_id == profile_edu.occupation_id:
            score += 10
    # Age preference: within 5 years (10). Need DOB from both.
    if viewer_pers and profile_pers and hasattr(profile_user, 'dob') and profile_user.dob and hasattr(viewer, 'dob') and viewer.dob:
        a1 = age_from_dob(viewer.dob)
        a2 = age_from_dob(profile_user.dob)
        if a1 is not None and a2 is not None and abs(a1 - a2) <= 5:
            score += 10
    # Base so we don't return 0 for everyone (30 base + up to 70 from above = 100)
    base = 30
    return min(100, base + score)


def build_user_match_score_sql_expression(viewer):
    """
    DB expression aligned with compute_match_percentage (0–100) for SQL ordering.
    """
    viewer_rel = UserReligion.objects.filter(user=viewer).only('religion_id').first()
    viewer_edu = UserEducation.objects.filter(user=viewer).only(
        'highest_education_id', 'occupation_id',
    ).first()
    viewer_loc = UserLocation.objects.filter(user=viewer).only('state_id').first()

    parts = [Value(30, output_field=IntegerField())]
    v_rid = viewer_rel.religion_id if viewer_rel else None
    if v_rid:
        parts.append(
            Case(
                When(user_religion__religion_id=v_rid, then=Value(20)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
    else:
        parts.append(Value(0, output_field=IntegerField()))
    v_eid = viewer_edu.highest_education_id if viewer_edu else None
    if v_eid:
        parts.append(
            Case(
                When(user_education__highest_education_id=v_eid, then=Value(15)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
    else:
        parts.append(Value(0, output_field=IntegerField()))
    v_sid = viewer_loc.state_id if viewer_loc else None
    if v_sid:
        parts.append(
            Case(
                When(user_location__state_id=v_sid, then=Value(15)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
    else:
        parts.append(Value(0, output_field=IntegerField()))
    v_oid = viewer_edu.occupation_id if viewer_edu else None
    if v_oid:
        parts.append(
            Case(
                When(user_education__occupation_id=v_oid, then=Value(10)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
    else:
        parts.append(Value(0, output_field=IntegerField()))
    va = None
    if getattr(viewer, 'dob', None):
        va = age_from_dob(viewer.dob)
    if va is not None:
        today = date.today()
        dob_lo = today - timedelta(days=int(365.25 * (va + 5)))
        dob_hi = today - timedelta(days=int(365.25 * max(0, va - 5)))
        if dob_lo <= dob_hi:
            parts.append(
                Case(
                    When(dob__gte=dob_lo, dob__lte=dob_hi, then=Value(10)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            )
        else:
            parts.append(Value(0, output_field=IntegerField()))
    else:
        parts.append(Value(0, output_field=IntegerField()))

    total = parts[0]
    for p in parts[1:]:
        total = total + p
    return total
