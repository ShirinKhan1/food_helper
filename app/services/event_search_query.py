from __future__ import annotations

from app.schemas.event import EventProfile
from app.services.event_profiles import EVENT_SEARCH_BOOST
from scripts.search.search_recipes import prepare_search_text


def build_event_search_query(message: str, event_profile: EventProfile) -> str:
    base = prepare_search_text(message, skip_normalize=False).strip()
    et = event_profile.event_type or "generic_event"
    boost = EVENT_SEARCH_BOOST.get(et) or EVENT_SEARCH_BOOST["generic_event"]
    return f"{base} {boost}".strip()
