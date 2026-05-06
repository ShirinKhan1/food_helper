from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QueryConstraints(BaseModel):
    dish: str | None = None
    include_ingredients: list[str] = Field(default_factory=list)
    exclude_ingredients: list[str] = Field(default_factory=list)
    allergy_exclusions: list[str] = Field(default_factory=list)
    dietary_preference: str | None = None
    restriction_type: str | None = None
    meal_type: str | None = None
    diet_goal: str | None = None
    max_calories_kcal: float | None = None
    min_protein_g: float | None = None
    max_fat_g: float | None = None
    max_cooking_time_minutes: int | None = None
    max_difficulty: int | None = None

    def merge(self, other: "QueryConstraints") -> "QueryConstraints":
        data: dict[str, Any] = self.model_dump()
        incoming = other.model_dump()
        for key, value in incoming.items():
            if isinstance(value, list):
                merged = list(dict.fromkeys([*data.get(key, []), *value]))
                data[key] = merged
            elif value is not None:
                data[key] = value
        return QueryConstraints.model_validate(data)


class SearchDebugItem(BaseModel):
    recipe_id: int
    title: str
    recipe_url: str
    similarity: float | None = None
    score: float | None = None
    matched_by: list[str] = Field(default_factory=list)


class SearchDebugRequest(BaseModel):
    query: str
    top_k: int = 10
    filters: QueryConstraints = Field(default_factory=QueryConstraints)


class SearchDebugResponse(BaseModel):
    normalized_query: str
    constraints: QueryConstraints
    vector_results: list[SearchDebugItem] = Field(default_factory=list)
    keyword_results: list[SearchDebugItem] = Field(default_factory=list)
    final_results: list[SearchDebugItem] = Field(default_factory=list)
