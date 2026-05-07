from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ParserIntent = Literal[
    "search_recipes",
    "recommend_recipes",
    "nutrition_question",
    "ingredient_substitution",
    "general_substitution",
    "recipe_details",
    "similar_recipes",
    "allergy_or_exclusion",
    "conversation_recall",
    "fallback",
]


class ParsedQueryConstraints(BaseModel):
    dish: str | None = None
    include_ingredients: list[str] = Field(default_factory=list)
    exclude_ingredients: list[str] = Field(default_factory=list)
    allergy_exclusions: list[str] = Field(default_factory=list)
    dietary_preference: str | None = None
    restriction_type: str | None = None
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] | None = None
    diet_goal: str | None = None
    max_calories_kcal: float | None = Field(default=None, ge=0, le=5000)
    min_protein_g: float | None = Field(default=None, ge=0, le=300)
    max_fat_g: float | None = Field(default=None, ge=0, le=300)
    max_cooking_time_minutes: int | None = Field(default=None, ge=1, le=1440)
    max_difficulty: int | None = Field(default=None, ge=1, le=5)


class RecipeReference(BaseModel):
    type: Literal["rank", "selected", "title", "unknown"]
    value: int | str | None = None


class ClarificationRequest(BaseModel):
    reason: str
    question: str
    expected_fields: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)


class ParsedUserRequest(BaseModel):
    intent: ParserIntent
    confidence: float = Field(ge=0, le=1)
    search_query: str | None = None
    constraints: ParsedQueryConstraints = Field(default_factory=ParsedQueryConstraints)
    recipe_reference: RecipeReference | None = None
    recipe_title_query: str | None = None
    target_ingredient: str | None = None
    nutrients: list[str] = Field(default_factory=list)
    requires_clarification: bool = False
    clarification: ClarificationRequest | None = None
