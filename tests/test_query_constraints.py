from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.orchestrator.query_constraints import extract_query_constraints
from scripts.search.query_normalize import normalize_query_for_search


def test_normalize_preserves_without_constraint_signal() -> None:
    out = normalize_query_for_search("борщ без мяса")
    assert "борщ" in out
    assert "мясо" in out


def test_extract_without_meat() -> None:
    result = extract_query_constraints("Какие есть рецепты борща без мяса?")
    assert result.exclude_ingredients == ["мясо"]


def test_extract_without_sugar() -> None:
    result = extract_query_constraints("рецепт без сахара")
    assert result.exclude_ingredients == ["сахар"]


def test_extract_include_chicken() -> None:
    result = extract_query_constraints("Посоветуй легкий ужин с курицей без грибов")
    assert result.include_ingredients == ["курица"]
    assert result.exclude_ingredients == ["гриб"]


def test_extract_include_chicken_from_recipe_phrase() -> None:
    result = extract_query_constraints("Сколько калорий и белка в рецепте с курицей?")
    assert result.include_ingredients == ["курица"]


def test_extract_include_chicken_fillet() -> None:
    result = extract_query_constraints("Что приготовить из куриного филе?")
    assert result.include_ingredients == ["курица"]


def test_extract_include_egg() -> None:
    result = extract_query_constraints("Найди рецепты с яйцом")
    assert result.include_ingredients == ["яйцо"]


def test_does_not_treat_general_substitution_as_include() -> None:
    result = extract_query_constraints("Чем заменить молоко?")
    assert result.include_ingredients == []
    assert result.exclude_ingredients == []


def test_extract_forbidden_milk() -> None:
    result = extract_query_constraints("мне нельзя молоко")
    assert result.exclude_ingredients == ["молоко"]
    assert result.restriction_type == "forbidden"


def test_extract_allergy_egg() -> None:
    result = extract_query_constraints("у меня аллергия на яйцо")
    assert result.allergy_exclusions == ["яйцо"]
    assert result.restriction_type == "allergy_or_forbidden"


def test_extract_light_breakfast_defaults() -> None:
    result = extract_query_constraints("Что можно приготовить на завтрак, чтобы оно было легкое?")
    assert result.meal_type == "breakfast"
    assert result.diet_goal == "light"
    assert result.max_calories_kcal == 150
    assert result.max_fat_g == 8
    assert result.max_cooking_time_minutes == 30
    assert result.max_difficulty == 2
