"""
Legacy UI helpers for chart + match cards (swisseph / Horoscope model).
Stubbed while horoscope data comes from the Windows EXE bridge (HoroscopeProfile).
"""


def _gender_key(user) -> str:
    """Normalize User.gender (M/F/O or blank) for porutham bride/groom resolution."""
    g = (getattr(user, 'gender', None) or '').strip().upper()
    if not g:
        return ''
    return g[0]


def kuja_dosham_horoscope(_horoscope):
    return False


def kendra_malefic_count_horoscope(_horoscope):
    return 0


def resolve_bride_groom_horoscopes(primary_profile, partner_profile, primary_h, partner_h):
    """
    Return (bride_h, groom_h) for Kerala Dashakoot.

    When both users have M/F, follow standard convention (female bride, male groom).
    When one gender is missing (common on partial profiles), infer from the known side
    so we do not treat the *page subject* as bride just because they appear first.
    """
    pg = _gender_key(primary_profile.user)
    og = _gender_key(partner_profile.user)
    if pg == 'F' and og == 'M':
        return primary_h, partner_h
    if pg == 'M' and og == 'F':
        return partner_h, primary_h
    if pg == 'F' and og != 'M':
        return primary_h, partner_h
    if og == 'F' and pg != 'M':
        return partner_h, primary_h
    if pg == 'M' and og != 'F':
        return partner_h, primary_h
    if og == 'M' and pg != 'F':
        return primary_h, partner_h
    return primary_h, partner_h


def build_person_card(_profile, _horoscope, _chart_url: str) -> dict:    return {}


def build_match_ui(
    _primary_profile,
    _partner_profile,
    _primary_h,
    _partner_h,
) -> dict:
    return {}
