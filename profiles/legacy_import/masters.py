"""Master-data resolver with in-run cache and legacy alias normalization.

The legacy export contains many spellings the new master tables don't have
(e.g. `Hindu` vs `Hinduism`, `ROMAN CATHLIC`, `Second Marriage`). The resolver
normalizes well-known aliases and `get_or_create`s anything new so that the
imported profile keeps a meaningful FK rather than dropping the value.
"""
from __future__ import annotations

from typing import Optional

from master.models import (
    Caste,
    City,
    Country,
    District,
    Education,
    EducationSubject,
    Height,
    IncomeRange,
    MaritalStatus,
    MotherTongue,
    Occupation,
    Religion,
    State,
)

from .normalize import clean

RELIGION_ALIASES = {
    "hindu": "Hinduism",
    "hinduism": "Hinduism",
    "christian": "Christianity",
    "christianity": "Christianity",
    "muslim": "Islam",
    "islam": "Islam",
}

COMPLEXION_ALIASES = {
    "white": "Very Fair",
    "medium": "Wheatish",
    "medium white": "Wheatish",
    "wheatish": "Wheatish",
    "wheatish brown": "Wheatish",
    "fair": "Fair",
    "very fair": "Very Fair",
    "dark": "Dark",
    "black": "Dark",
    "other": "",
}


def normalize_religion_name(raw: object) -> str:
    text = clean(raw)
    if not text:
        return ""
    return RELIGION_ALIASES.get(text.lower(), text)


def normalize_complexion_name(raw: object) -> str:
    text = clean(raw)
    if not text:
        return ""
    return COMPLEXION_ALIASES.get(text.lower(), text)


class MasterResolver:
    """Cache + alias-aware get_or_create for every master FK we touch.

    `auto_create=False` (the dry-run case) returns existing rows only and
    leaves missing values as None so we don't pollute master tables when
    just validating.
    """

    def __init__(self, auto_create: bool = True):
        self.auto_create = auto_create
        self.cache: dict[tuple, object] = {}

    def _named(self, model, name: str, **filters):
        if not name:
            return None
        cache_key = (model, tuple(sorted((k, getattr(v, "pk", v)) for k, v in filters.items())), name.lower())
        if cache_key in self.cache:
            return self.cache[cache_key]
        obj = model.objects.filter(name__iexact=name, **filters).first()
        if not obj and self.auto_create:
            obj = model.objects.create(name=name, is_active=True, **filters)
        self.cache[cache_key] = obj
        return obj

    def named(self, model, raw: object, **filters):
        return self._named(model, clean(raw, zero_is_blank=True), **filters)

    def religion(self, raw: object) -> Optional[Religion]:
        return self._named(Religion, normalize_religion_name(raw))

    def caste(self, religion: Optional[Religion], raw: object) -> Optional[Caste]:
        if not religion:
            return None
        return self._named(Caste, clean(raw), religion=religion)

    def mother_tongue(self, raw: object) -> Optional[MotherTongue]:
        return self._named(MotherTongue, clean(raw))

    def marital_status(self, raw: object) -> Optional[MaritalStatus]:
        return self._named(MaritalStatus, clean(raw))

    def education(self, raw: object) -> Optional[Education]:
        return self._named(Education, clean(raw))

    def education_subject(self, raw: object) -> Optional[EducationSubject]:
        return self._named(EducationSubject, clean(raw))

    def occupation(self, raw: object) -> Optional[Occupation]:
        return self._named(Occupation, clean(raw))

    def income_range(self, raw: object) -> Optional[IncomeRange]:
        return self._named(IncomeRange, clean(raw))

    def location(
        self,
        country: object,
        state: object,
        district: object,
        city: object,
    ) -> tuple[Optional[Country], Optional[State], Optional[District], Optional[City]]:
        c = self._named(Country, clean(country))
        s = self._named(State, clean(state), country=c) if c else None
        d = self._named(District, clean(district), state=s) if s else None
        ci = self._named(City, clean(city), district=d) if d else None
        return c, s, d, ci

    def height(self, cm: Optional[int]) -> Optional[Height]:
        if not cm or cm < 100 or cm > 250:
            return None
        cache_key = ("height", cm)
        if cache_key in self.cache:
            return self.cache[cache_key]
        obj, _ = Height.objects.get_or_create(
            value_cm=cm,
            defaults={"display_label": f"{cm} cm", "is_active": True},
        )
        self.cache[cache_key] = obj
        return obj
