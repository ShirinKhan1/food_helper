from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.db import Database
from app.services.recipe_repository import RecipeRepository


def test_row_to_recipe_card_and_detail() -> None:
    row = {
        "id": 7,
        "title": "Омлет",
        "description": "Быстрый завтрак",
        "calories_kcal": 146.27,
        "protein_g": 11.05,
        "fat_g": 3.79,
        "carbs_g": 16.64,
        "servings": 2,
        "recipe_url": "https://example.com/omelet",
        "properties": {
            "Время на кухне": "10 минут",
            "Сложность": "1 из 5",
            "Аллергены": ["Яйцо", "Молоко"],
        },
        "ingredients": [{"name": "Яйцо", "quantity": "2 шт", "block": "Для блюда"}],
        "steps": [{"position": 1, "title": "Шаг 1", "text": "Взбейте яйца"}],
    }
    repository = RecipeRepository(Database("postgresql://unused"))

    card = repository.row_to_recipe_card(row, rank=1)
    assert card.recipe_id == 7
    assert card.cooking_time == "10 минут"
    assert card.difficulty == "1 из 5"
    assert card.allergens == ["Яйцо", "Молоко"]

    detail = repository.row_to_recipe_detail(row)
    assert detail.recipe_id == 7
    assert detail.ingredients[0].name == "Яйцо"
    assert detail.steps[0].text == "Взбейте яйца"
    assert detail.nutrition.calories_kcal == 146.27
