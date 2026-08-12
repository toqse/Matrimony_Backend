"""Filter profiles by planet house from Lagnam on the EXE rasi chart (pr_rasi)."""
from __future__ import annotations

from astrology.models import HoroscopeProfile
from astrology.porutham import chart_to_array, ras_dif

# 1-based chart_to_array index for each canonical planet key (EXE order).
PLANET_KEY_TO_INDEX: dict[str, int] = {
    "lagnam": 1,
    "ravi": 2,
    "chandran": 3,
    "kuja": 4,
    "budhan": 5,
    "guru": 6,
    "sukran": 7,
    "sani": 8,
    "rahu": 9,
    "kethu": 10,
    "maandi": 11,
}


def planet_house_from_lagna(pr_rasi: str | None, planet_key: str) -> int | None:
    """
    Return the bhava (1-12) of ``planet_key`` counted from Lagnam on ``pr_rasi``.
    Returns None when the chart string or planet key is invalid.
    """
    key = (planet_key or "").strip().lower()
    idx = PLANET_KEY_TO_INDEX.get(key)
    if idx is None or not pr_rasi or len(pr_rasi) < 11:
        return None
    arr = chart_to_array(pr_rasi)
    if len(arr) < 12:
        return None
    lagna_sign = arr[1]
    planet_sign = arr[idx]
    if not (1 <= lagna_sign <= 12 and 1 <= planet_sign <= 12):
        return None
    return ras_dif(lagna_sign, planet_sign)


def filter_users_by_planet_house(qs, planet_key: str, house_num: int):
    """
    Keep only users in ``qs`` whose rasi chart places ``planet_key`` in ``house_num``
    from Lagnam. Returns the narrowed queryset (possibly empty).
    """
    # Subquery — avoid materializing every candidate pk in Python before scanning charts.
    matching_ids: list = []
    for hp in (
        HoroscopeProfile.objects.filter(user_id__in=qs.values("pk"))
        .exclude(pr_rasi="")
        .filter(pr_rasi__isnull=False)
        .only("user_id", "pr_rasi")
        .iterator(chunk_size=500)
    ):
        if len(hp.pr_rasi) < 11:
            continue
        house = planet_house_from_lagna(hp.pr_rasi, planet_key)
        if house == house_num:
            matching_ids.append(hp.user_id)

    if not matching_ids:
        return qs.none()
    return qs.filter(pk__in=matching_ids)
