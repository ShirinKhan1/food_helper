from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.schemas.recipe import NutritionInfo, RecipeDetail, RecipeIngredient
from app.services.ingredient_catalog import IngredientCatalog
from app.services.substitution import SubstitutionService


def test_substitution_returns_rule_based_options() -> None:
    recipe = RecipeDetail(
        recipe_id=1,
        title="Запеканка",
        ingredients=[RecipeIngredient(name="Сахар", quantity="100 г", block="Для блюда")],
        steps=[],
        nutrition=NutritionInfo(),
        properties={},
        servings=2,
        recipe_url="https://example.com",
    )
    service = SubstitutionService(IngredientCatalog.load())

    result = service.suggest(recipe, "сахар")

    assert result.found_in_recipe is True
    assert result.options
    assert result.options[0].name
    assert result.warnings


def test_general_substitution_returns_rule_based_options() -> None:
    service = SubstitutionService(IngredientCatalog.load())

    result = service.suggest_general("молоко")

    assert result.found_in_recipe is True
    assert result.options
    assert result.options[0].name == "растительное молоко"
    assert result.warnings


def test_general_substitution_empty_rules_has_warning() -> None:
    service = SubstitutionService(IngredientCatalog.load())

    result = service.suggest_general("шафран")

    assert result.options == []
    assert any("нет готового" in warning for warning in result.warnings)
