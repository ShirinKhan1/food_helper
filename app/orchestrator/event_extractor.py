from __future__ import annotations

import re

from app.schemas.event import EventProfile
from app.services.event_profiles import (
    ALLOWED_EVENT_TYPES,
    EVENT_PROFILES,
    EVENT_TYPE_ORDER,
    profile_defaults,
)

GUESTS_RE = re.compile(
    r"(?:на|для|будет|нас\s+будет)\s+(\d{1,2})\s*(?:человек|чел\.?|гост|друга|друзей|персон|персоны)?",
    re.IGNORECASE,
)


def _normalize_event_type(raw: str | None) -> str | None:
    if not raw:
        return None
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if key in ALLOWED_EVENT_TYPES:
        return key
    return None


def extract_guests_count(message: str, *, max_guests: int) -> int | None:
    match = GUESTS_RE.search(message)
    if not match:
        return None
    n = int(match.group(1))
    if n < 1 or n > max_guests:
        return None
    return n


def extract_event_profile(message: str, *, max_guests: int = 30) -> EventProfile | None:
    lowered = " ".join(message.lower().split())
    matched_type: str | None = None
    for event_type in EVENT_TYPE_ORDER:
        profile = EVENT_PROFILES.get(event_type)
        if not profile:
            continue
        for kw in profile.get("keywords") or []:
            if kw.strip().lower() in lowered:
                matched_type = event_type
                break
        if matched_type:
            break

    if not matched_type:
        return None

    guests = extract_guests_count(message, max_guests=max_guests)
    defaults = profile_defaults(matched_type)
    return EventProfile(
        event_type=matched_type,
        guests_count=guests,
        format=defaults.get("format"),
        vibe=list(defaults.get("vibe") or []),
        meal_roles=list(defaults.get("meal_roles") or []),
        preparation_style=None,
    )


def merge_event_profiles(base: EventProfile | None, override: EventProfile | None) -> EventProfile | None:
    if base is None and override is None:
        return None
    if base is None:
        return override
    if override is None:
        return base
    et = override.event_type or base.event_type
    guests = override.guests_count if override.guests_count is not None else base.guests_count
    fmt = override.format or base.format
    vibe = list(dict.fromkeys([*base.vibe, *override.vibe]))
    roles = override.meal_roles if override.meal_roles else base.meal_roles
    prep = override.preparation_style or base.preparation_style
    out = EventProfile(
        event_type=et,
        guests_count=guests,
        format=fmt,
        vibe=vibe,
        meal_roles=list(roles),
        preparation_style=prep,
    )
    if out.event_type and out.event_type != "generic_event" and not out.meal_roles:
        d = profile_defaults(out.event_type)
        out = out.model_copy(update={"meal_roles": list(d.get("meal_roles") or []), "format": out.format or d.get("format")})
    return out


def coerce_event_profile_dict(data: dict | None, *, max_guests: int) -> EventProfile | None:
    if not data:
        return None
    raw_et = data.get("event_type")
    if raw_et is None or (isinstance(raw_et, str) and not raw_et.strip()):
        et: str | None = None
    else:
        et = _normalize_event_type(str(raw_et))
        if et is None:
            et = "generic_event"

    guests = data.get("guests_count")
    if guests is not None:
        try:
            gi = int(guests)
            if gi < 1 or gi > max_guests:
                guests = None
            else:
                guests = gi
        except (TypeError, ValueError):
            guests = None
    return EventProfile(
        event_type=et,
        guests_count=guests,
        format=data.get("format"),
        vibe=list(data.get("vibe") or []),
        meal_roles=list(data.get("meal_roles") or []),
        preparation_style=data.get("preparation_style"),
    )
