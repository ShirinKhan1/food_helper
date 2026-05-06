from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.schemas.search import QueryConstraints
from app.services.hybrid_search import HybridSearchService
from app.services.ingredient_catalog import IngredientCatalog


class FakeVectorSearch:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def search(self, query_embedding: list[float], *, top_k: int) -> list[dict]:
        return self._rows[:top_k]


class FakeKeywordSearch:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def search(self, normalized_query: str, *, top_k: int) -> list[dict]:
        return self._rows[:top_k]


def _service(rows: list[dict]) -> HybridSearchService:
    return HybridSearchService(
        vector_search=FakeVectorSearch(rows),
        keyword_search=FakeKeywordSearch([]),
        ingredient_catalog=IngredientCatalog.load(),
    )


def test_hard_filter_uses_structured_ingredients_for_exclusions() -> None:
    rows = [
        {
            "id": 1,
            "title": "Постный борщ",
            "description": "Борщ без мяса",
            "recipe_url": "https://example.com/lean",
            "similarity": 0.9,
            "ingredients": [{"name": "Свекла"}, {"name": "Капуста"}],
        },
        {
            "id": 2,
            "title": "Борщ с говядиной",
            "description": "Классический борщ",
            "recipe_url": "https://example.com/meat",
            "similarity": 0.8,
            "ingredients": [{"name": "Говядина"}, {"name": "Свекла"}],
        },
    ]

    execution = _service(rows).run(
        normalized_query="борщ мясо",
        query_embedding=[0.0],
        constraints=QueryConstraints(exclude_ingredients=["мясо"]),
        top_k=5,
    )

    assert [row["id"] for row in execution.final_results] == [1]


def test_similar_filter_applies_allergy_exclusions_to_final_results() -> None:
    rows = [
        {
            "id": 1,
            "title": "Омлет",
            "recipe_url": "https://example.com/omelet",
            "similarity": 0.9,
            "ingredients": [{"name": "Яйцо"}],
        },
        {
            "id": 2,
            "title": "Овсянка",
            "recipe_url": "https://example.com/oatmeal",
            "similarity": 0.8,
            "ingredients": [{"name": "Овсянка"}],
        },
    ]

    execution = _service([]).filter_similar(
        rows,
        normalized_query="похожее без яйца",
        constraints=QueryConstraints(allergy_exclusions=["яйцо"]),
        top_k=5,
    )

    assert [row["id"] for row in execution.final_results] == [2]


def test_hard_filter_checks_recipe_allergen_characteristics() -> None:
    rows = [
        {
            "id": 1,
            "title": "Чизкейк без теста",
            "recipe_url": "https://example.com/cheesecake",
            "similarity": 0.9,
            "properties": {"Аллергены": ["Белок коровьего молока", "Злаки", "содержащие глютен"]},
            "ingredients": [{"name": "Печенье"}, {"name": "Творожный сыр"}],
        },
        {
            "id": 2,
            "title": "Помидоры на зиму",
            "recipe_url": "https://example.com/tomatoes",
            "similarity": 0.8,
            "properties": {"Аллергены": ["Нет"]},
            "ingredients": [{"name": "Помидоры"}, {"name": "Уксус"}],
        },
    ]

    execution = _service(rows).run(
        normalized_query="рецепт без злак",
        query_embedding=[0.0],
        constraints=QueryConstraints(exclude_ingredients=["злак"]),
        top_k=5,
    )

    assert [row["id"] for row in execution.final_results] == [2]


def test_hard_filter_matches_inflected_allergen_words() -> None:
    rows = [
        {
            "id": 1,
            "title": "Сливочный десерт",
            "recipe_url": "https://example.com/dessert",
            "similarity": 0.9,
            "properties": {"Аллергены": ["Белок коровьего молока"]},
            "ingredients": [{"name": "Сливки"}],
        },
        {
            "id": 2,
            "title": "Фруктовый лед",
            "recipe_url": "https://example.com/ice",
            "similarity": 0.8,
            "properties": {"Аллергены": ["Нет"]},
            "ingredients": [{"name": "Ягоды"}],
        },
    ]

    execution = _service(rows).run(
        normalized_query="рецепт без молоко",
        query_embedding=[0.0],
        constraints=QueryConstraints(exclude_ingredients=["молоко"]),
        top_k=5,
    )

    assert [row["id"] for row in execution.final_results] == [2]
