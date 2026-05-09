from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.schemas.event import EventProfile
from app.schemas.recipe import RecipeCard
from app.services.menu_composer import MenuComposer


def _card(rid: int, rank: int) -> RecipeCard:
    return RecipeCard(
        rank=rank,
        recipe_id=rid,
        title=f"Recipe {rid}",
        recipe_url=f"https://example.com/{rid}",
    )


def _row(rid: int, score: float, roles: list[str]) -> dict:
    return {"id": rid, "title": f"R{rid}", "event_score": score, "event_roles": roles, "recipe_url": f"https://x/{rid}"}


def test_menu_no_duplicate_recipe_ids() -> None:
    composer = MenuComposer()
    profile = EventProfile(
        event_type="new_year",
        meal_roles=["starter", "salad", "main"],
        vibe=[],
    )
    rows = [
        _row(1, 0.9, ["starter"]),
        _row(2, 0.85, ["salad"]),
        _row(3, 0.8, ["main"]),
        _row(4, 0.7, ["main"]),
    ]

    def row_to_card(row: dict, *, rank: int) -> RecipeCard:
        return _card(int(row["id"]), rank)

    menu = composer.compose(ranked_rows=rows, event_profile=profile, top_k=5, row_to_card=row_to_card)
    seen: set[int] = set()
    for g in menu:
        for c in g.recipes:
            assert c.recipe_id not in seen
            seen.add(c.recipe_id)


def test_menu_skips_empty_groups() -> None:
    composer = MenuComposer()
    profile = EventProfile(event_type="new_year", meal_roles=["starter", "soup"], vibe=[])
    rows = [_row(1, 0.9, ["starter"])]
    menu = composer.compose(
        ranked_rows=rows,
        event_profile=profile,
        top_k=5,
        row_to_card=lambda r, *, rank: _card(int(r["id"]), rank),
    )
    assert len(menu) == 1
    assert menu[0].role == "starter"
