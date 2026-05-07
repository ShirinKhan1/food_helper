from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.recipe import NutritionInfo, RecipeCard, RecipeDetail, SourceInfo, SubstitutionOption
from app.schemas.search import QueryConstraints


@dataclass(frozen=True)
class LLMAnswerContext:
    scenario: str
    user_message: str
    constraints: QueryConstraints | None = None
    recipes: list[RecipeCard] = field(default_factory=list)
    recipe_detail: RecipeDetail | None = None
    nutrition: NutritionInfo | None = None
    substitutions: list[SubstitutionOption] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sources: list[SourceInfo] = field(default_factory=list)
    detail_mode: str | None = None
