from __future__ import annotations

from typing import Any

from app.services.recipe_repository import RecipeRepository


class KeywordSearchService:
    def __init__(self, recipe_repository: RecipeRepository) -> None:
        self._recipe_repository = recipe_repository

    def search(self, query: str, *, top_k: int) -> list[dict[str, Any]]:
        return self._recipe_repository.search_recipe_rows_by_text(query, limit=top_k)
