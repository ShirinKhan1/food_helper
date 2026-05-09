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


def test_route_general_substitution_without_recipe() -> None:
    decision = IntentRouter().decide("Чем заменить молоко?")
    assert decision.intent == "general_substitution"
    assert decision.route == "substitution_catalog"
    assert decision.entities["target_ingredient"] == "молоко"


def test_without_milk_is_search_constraint_not_substitution() -> None:
    decision = IntentRouter().decide("Найди рецепт без молока")
    assert decision.intent == "search_recipes"
    assert decision.route == "hybrid_search"
    assert decision.entities["exclude_ingredients"] == ["молоко"]


def test_route_recommendation() -> None:
    decision = IntentRouter().decide("Что можно приготовить на завтрак, чтобы оно было легкое?")
    assert decision.intent == "recommend_recipes"
    assert decision.route == "hybrid_search"


def test_route_event_new_year() -> None:
    decision = IntentRouter().decide("Подбери рецепты на Новый год для 6 человек")
    assert decision.intent == "event_recommendation"
    assert decision.route == "event_menu_recommendation"
    assert decision.entities.get("event_profile", {}).get("event_type") == "new_year"


def test_route_event_date_night_excludes() -> None:
    decision = IntentRouter().decide("Хочу романтический ужин без морепродуктов")
    assert decision.intent == "event_recommendation"
    exc = decision.entities.get("exclude_ingredients") or []
    assert any("морепродукт" in str(x).lower() for x in exc)


def test_route_nutrition() -> None:
    decision = IntentRouter().decide("Сколько калорий в яблочном пироге?")
    assert decision.intent == "nutrition_question"
    assert decision.entities["nutrient"] == "calories"
    assert decision.entities["recipe_title_query"] == "яблочном пироге"


def test_route_multi_nutrition_with_ingredient_constraint() -> None:
    decision = IntentRouter().decide("Сколько калорий и белка в рецепте с курицей?")
    assert decision.intent == "nutrition_question"
    assert decision.entities["nutrient"] == "bju"
    assert decision.entities["include_ingredients"] == ["курица"]


def test_route_recipe_details() -> None:
    decision = IntentRouter().decide("Покажи второй рецепт")
    assert decision.intent == "recipe_details"
    assert decision.route == "conversation_recipe_fetch"


def test_route_recipe_details_by_title_followup() -> None:
    decision = IntentRouter().decide("Расскажи подробнее про шоколадный напиток")
    assert decision.intent == "recipe_details"
    assert decision.route == "conversation_recipe_fetch"
    assert decision.entities["recipe_title_query"] == "шоколадный напиток"
