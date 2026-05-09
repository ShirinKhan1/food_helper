from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.schemas.event import EventProfile
from app.schemas.search import QueryConstraints
from app.services.event_ranker import EventRanker


def _row(
    *,
    rid: int,
    title: str,
    category: str = "",
    subcategory: str = "",
    servings: int | None = 4,
    ingredients: list | None = None,
    steps: list | None = None,
    properties: dict | None = None,
) -> dict:
    return {
        "id": rid,
        "title": title,
        "description": "",
        "category": category,
        "subcategory": subcategory,
        "servings": servings,
        "ingredients": ingredients or [],
        "steps": steps or [],
        "properties": properties or {},
        "calories_kcal": 200.0,
        "fat_g": 10.0,
        "recipe_url": f"https://example.com/{rid}",
    }


def test_finger_food_scores_higher_for_friends() -> None:
    ranker = EventRanker()
    salad = _row(rid=1, title="Овощной салат", category="Салаты")
    wings = _row(
        rid=2,
        title="Куриные крылышки к пиву",
        category="Закуски",
        ingredients=[{"name": "курица"}],
    )
    profile = EventProfile(
        event_type="friends_gathering",
        guests_count=6,
        meal_roles=["starter", "snack", "main"],
        vibe=["finger_food", "shareable", "easy"],
    )
    ranked = ranker.rank(rows=[salad, wings], event_profile=profile, constraints=QueryConstraints(), top_k=5)
    assert ranked[0]["id"] == 2


def test_romantic_bonus_for_date_night() -> None:
    ranker = EventRanker()
    pasta = _row(
        rid=10,
        title="Паста карбонара",
        ingredients=[{"name": "паста"}, {"name": "сыр"}],
    )
    soup = _row(rid=11, title="Суп лапша", category="Супы")
    profile = EventProfile(
        event_type="date_night",
        meal_roles=["main", "dessert"],
        vibe=["romantic", "light", "beautiful"],
    )
    ranked = ranker.rank(rows=[soup, pasta], event_profile=profile, constraints=QueryConstraints(), top_k=5)
    assert ranked[0]["id"] == 10


def test_servings_penalty_when_small_batch() -> None:
    ranker = EventRanker()
    small = _row(rid=3, title="Порция на двоих", servings=2)
    big = _row(rid=4, title="Большое блюдо", servings=8)
    profile = EventProfile(
        event_type="birthday",
        guests_count=8,
        meal_roles=["main"],
        vibe=["shareable"],
    )
    ranked = ranker.rank(rows=[small, big], event_profile=profile, constraints=QueryConstraints(), top_k=5)
    assert ranked[0]["id"] == 4


def test_high_difficulty_penalty() -> None:
    ranker = EventRanker()
    hard = _row(rid=5, title="Сложный торт", category="Торты", properties={"Сложность": "5 из 5"})
    easy = _row(rid=6, title="Простой салат", category="Салаты", properties={"Сложность": "2 из 5"})
    profile = EventProfile(
        event_type="friends_gathering",
        meal_roles=["main", "salad"],
        vibe=["easy"],
    )
    ranked = ranker.rank(rows=[hard, easy], event_profile=profile, constraints=QueryConstraints(), top_k=5)
    assert ranked[0]["id"] == 6
