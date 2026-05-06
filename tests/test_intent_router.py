from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.orchestrator.intent_router import IntentRouter


def test_route_search_recipes() -> None:
    decision = IntentRouter().decide("Какие есть рецепты борща без мяса?")
    assert decision.intent == "search_recipes"
    assert decision.route == "hybrid_search"
    assert decision.entities["exclude_ingredients"] == ["мясо"]


def test_route_substitution_with_rank_reference() -> None:
    decision = IntentRouter().decide("На что в третьем рецепте можно заменить сахар?")
    assert decision.intent == "ingredient_substitution"
    assert decision.entities["recipe_reference"] == {"type": "rank", "value": 3}
    assert decision.entities["target_ingredient"] == "сахар"


def test_route_recommendation() -> None:
    decision = IntentRouter().decide("Что можно приготовить на завтрак, чтобы оно было легкое?")
    assert decision.intent == "recommend_recipes"
    assert decision.route == "hybrid_search"


def test_route_nutrition() -> None:
    decision = IntentRouter().decide("Сколько калорий в яблочном пироге?")
    assert decision.intent == "nutrition_question"
    assert decision.entities["nutrient"] == "calories"
    assert decision.entities["recipe_title_query"] == "яблочном пироге"


def test_route_recipe_details() -> None:
    decision = IntentRouter().decide("Покажи второй рецепт")
    assert decision.intent == "recipe_details"
    assert decision.route == "conversation_recipe_fetch"
