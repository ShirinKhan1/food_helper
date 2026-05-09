from __future__ import annotations

from app.orchestrator.dialog_follow_up import apply_follow_up_context, is_more_recipes_follow_up
from app.schemas.chat import IntentDecision
from app.schemas.search import QueryConstraints
from app.services.conversation_state import ConversationSnapshot


def _base_decision(*, intent: str = "search_recipes") -> IntentDecision:
    return IntentDecision(
        intent=intent,  # type: ignore[arg-type]
        route="hybrid_search",
        entities={},
        needs_conversation_context=False,
        needs_recipe_fetch=False,
        needs_vector_search=True,
        needs_sql=True,
        needs_llm=False,
    )


def test_is_more_recipes_follow_up_detects_short_continuation() -> None:
    assert is_more_recipes_follow_up("Какие можешь предложить еще рецепты")
    assert is_more_recipes_follow_up("Что ещё можно приготовить?")
    assert not is_more_recipes_follow_up("Подбери рецепты на Новый год для 6 человек")


def test_apply_follow_up_restores_event_menu_intent() -> None:
    ep = {"event_type": "new_year", "guests_count": 6, "meal_roles": ["main", "dessert"]}
    snap = ConversationSnapshot(
        conversation_id="c1",
        last_recipe_results=[10, 11, 12],
        last_event_profile=ep,
    )
    decision, constraints, msg, excl, clear_ep = apply_follow_up_context(
        message="Какие ещё рецепты предложишь?",
        snapshot=snap,
        decision=_base_decision(),
        constraints=QueryConstraints(),
        message_for_search="Какие ещё рецепты предложишь?",
        event_recommendation_enabled=True,
    )
    assert decision.intent == "event_recommendation"
    assert decision.route == "event_menu_recommendation"
    got_ep = decision.entities.get("event_profile") or {}
    assert got_ep.get("event_type") == "new_year"
    assert got_ep.get("guests_count") == 6
    assert excl == frozenset({10, 11, 12})
    assert clear_ep is False
    assert "new_year" in msg or "год" in msg.lower()


def test_apply_follow_up_excludes_ids_for_plain_list_continuation() -> None:
    snap = ConversationSnapshot(
        conversation_id="c2",
        last_recipe_results=[1, 2],
        last_event_profile=None,
    )
    decision, constraints, msg, excl, clear_ep = apply_follow_up_context(
        message="Покажи ещё варианты",
        snapshot=snap,
        decision=_base_decision(),
        constraints=QueryConstraints(),
        message_for_search="Покажи ещё варианты",
        event_recommendation_enabled=True,
    )
    assert decision.intent == "search_recipes"
    assert excl == frozenset({1, 2})
    assert clear_ep is False


def test_apply_follow_up_clears_event_on_new_search() -> None:
    snap = ConversationSnapshot(
        conversation_id="c3",
        last_recipe_results=[1],
        last_event_profile={"event_type": "new_year", "guests_count": 4},
    )
    decision, _, _, excl, clear_ep = apply_follow_up_context(
        message="Найди рецепт борща без мяса",
        snapshot=snap,
        decision=_base_decision(),
        constraints=QueryConstraints(),
        message_for_search="Найди рецепт борща без мяса",
        event_recommendation_enabled=True,
    )
    assert clear_ep is True
    assert excl is None
