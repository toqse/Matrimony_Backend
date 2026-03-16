"""
Match list: age from dob, height value, match percentage.
"""
from datetime import date
from django.db.models import Q


def age_from_dob(dob):
    if not dob:
        return None
    today = date.today()
    return (today - dob).days // 365


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
