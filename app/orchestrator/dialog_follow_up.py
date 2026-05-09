from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.schemas.chat import IntentDecision
from app.schemas.event import EventProfile
from app.schemas.search import QueryConstraints
from app.services.event_search_query import build_event_search_query

if TYPE_CHECKING:
    from app.services.conversation_state import ConversationSnapshot

_MORE_PATTERNS = (
    r"\bещ[её]\b",
    r"\bдруг(ие|их)\s+рецепт",
    r"какие\s+ещ[её]",
    r"что\s+ещ[её]",
    r"покаж\w*\s+ещ[её]",
    r"вариант\w*\s+ещ[её]",
    r"рецепт\w*\s+ещ[её]",
    r"ещ[её]\s+вариант",
    r"дополнительн\w*\s+рецепт",
    r"порекоменд\w*\s+ещ[её]",
    r"предлож\w*\s+ещ[её]",
)
_COMPILED = tuple(re.compile(p, re.IGNORECASE) for p in _MORE_PATTERNS)


def is_more_recipes_follow_up(message: str, *, max_chars: int = 120) -> bool:
    """Short follow-up asking for more / other recipes (continuation of last list or menu)."""
    one = " ".join(message.strip().split())
    if len(one) > max_chars:
        return False
    lowered = one.lower()
    return any(p.search(lowered) for p in _COMPILED)


def apply_follow_up_context(
    *,
    message: str,
    snapshot: ConversationSnapshot,
    decision: IntentDecision,
    constraints: QueryConstraints,
    message_for_search: str,
    event_recommendation_enabled: bool,
) -> tuple[IntentDecision, QueryConstraints, str, frozenset[int] | None, bool]:
    """
    Returns:
        decision, constraints, message_for_search, exclude_recipe_ids, clear_last_event_profile

    clear_last_event_profile: drop persisted event menu context (new standalone search).
    """
    clear_last_event_profile = False
    exclude: frozenset[int] | None = None

    if (
        snapshot.last_event_profile
        and is_more_recipes_follow_up(message)
        and event_recommendation_enabled
        and decision.intent in {"search_recipes", "recommend_recipes", "allergy_or_exclusion"}
    ):
        try:
            ep = EventProfile.model_validate(snapshot.last_event_profile)
        except Exception:
            ep = None
        if ep is not None:
            entities = dict(decision.entities or {})
            entities["event_profile"] = ep.model_dump(mode="json", exclude_none=True)
            decision = IntentDecision(
                intent="event_recommendation",
                route="event_menu_recommendation",
                entities=entities,
                needs_conversation_context=False,
                needs_recipe_fetch=False,
                needs_vector_search=True,
                needs_sql=True,
                needs_llm=False,
            )
            message_for_search = build_event_search_query(message, ep)
            exclude = frozenset(snapshot.last_recipe_results)
            return decision, constraints, message_for_search, exclude, False

    if decision.intent in {"search_recipes", "recommend_recipes", "allergy_or_exclusion"}:
        if is_more_recipes_follow_up(message) and snapshot.last_recipe_results:
            exclude = frozenset(snapshot.last_recipe_results)
        if snapshot.last_event_profile is not None and not is_more_recipes_follow_up(message):
            clear_last_event_profile = True

    return decision, constraints, message_for_search, exclude, clear_last_event_profile
