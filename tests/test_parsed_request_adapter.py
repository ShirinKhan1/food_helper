from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.config import Settings
from app.orchestrator.intent_router import IntentRouter
from app.orchestrator.parsed_request_adapter import ParsedRequestAdapter
from app.schemas.chat import IntentDecision
from app.schemas.parser import ParsedQueryConstraints, ParsedUserRequest, RecipeReference
from app.schemas.search import QueryConstraints


def _adapter(threshold: float = 0.65) -> ParsedRequestAdapter:
    base = Settings.from_env()
    return ParsedRequestAdapter(settings=replace(base, llm_query_parser_confidence_threshold=threshold))


def test_adapter_low_confidence_keeps_rule_intent() -> None:
    ad = _adapter(0.9)
    rule = IntentDecision(
        intent="search_recipes",
        route="hybrid_search",
        entities={"recipe_reference": None},
        needs_vector_search=True,
        needs_sql=True,
    )
    parsed = ParsedUserRequest(
        intent="recommend_recipes",
        confidence=0.5,
        constraints=ParsedQueryConstraints(),
    )
    d, c, msg = ad.to_pipeline_inputs(
        parsed=parsed,
        rule_decision=rule,
        rule_constraints=QueryConstraints(),
        message="тест",
    )
    assert d.intent == "search_recipes"


def test_adapter_fallback_plus_high_confidence_uses_llm_intent() -> None:
    ad = _adapter()
    rule = IntentDecision(intent="fallback", route="no_retrieval", entities={})
    parsed = ParsedUserRequest(
        intent="recommend_recipes",
        confidence=0.9,
        constraints=ParsedQueryConstraints(meal_type="dinner"),
    )
    d, c, msg = ad.to_pipeline_inputs(
        parsed=parsed,
        rule_decision=rule,
        rule_constraints=QueryConstraints(),
        message="ужин",
    )
    assert d.intent == "recommend_recipes"
    assert c.meal_type == "dinner"


def test_adapter_merges_rule_excludes() -> None:
    ad = _adapter()
    rule = IntentDecision(
        intent="search_recipes",
        route="hybrid_search",
        entities={},
        needs_vector_search=True,
        needs_sql=True,
    )
    rules_q = QueryConstraints(exclude_ingredients=["грибы"])
    parsed = ParsedUserRequest(
        intent="search_recipes",
        confidence=1.0,
        constraints=ParsedQueryConstraints(include_ingredients=["курица"]),
    )
    d, c, msg = ad.to_pipeline_inputs(
        parsed=parsed,
        rule_decision=rule,
        rule_constraints=rules_q,
        message="курица",
    )
    assert "грибы" in c.exclude_ingredients
    assert "курица" in c.include_ingredients


def test_adapter_recipe_reference_in_entities() -> None:
    ad = _adapter()
    rule = IntentDecision(
        intent="nutrition_question",
        route="sql",
        entities={},
        needs_sql=True,
    )
    parsed = ParsedUserRequest(
        intent="nutrition_question",
        confidence=1.0,
        recipe_reference=RecipeReference(type="rank", value=2),
        nutrients=["protein"],
        constraints=ParsedQueryConstraints(),
    )
    d, _, _ = ad.to_pipeline_inputs(
        parsed=parsed,
        rule_decision=rule,
        rule_constraints=QueryConstraints(),
        message="белок",
    )
    assert d.entities.get("recipe_reference") == {"type": "rank", "value": 2}
    assert d.entities.get("nutrient") == "protein"


def test_adapter_event_recommendation_route() -> None:
    from app.schemas.event import EventProfile

    ad = _adapter()
    rule = IntentRouter().decide("Меню на пикник на природе")
    parsed = ParsedUserRequest(
        intent="event_recommendation",
        confidence=1.0,
        event_profile=EventProfile(event_type="picnic"),
        constraints=ParsedQueryConstraints(),
    )
    d, _, _ = ad.to_pipeline_inputs(
        parsed=parsed,
        rule_decision=rule,
        rule_constraints=QueryConstraints(),
        message="Меню на пикник на природе",
    )
    assert d.intent == "event_recommendation"
    assert d.route == "event_menu_recommendation"
    assert d.entities.get("event_profile", {}).get("event_type") == "picnic"
