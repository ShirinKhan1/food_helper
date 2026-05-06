from __future__ import annotations

from pydantic import BaseModel, Field


class NutritionInfo(BaseModel):
    calories_kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbs_g: float | None = None
    serving_size: str | None = None


class RecipeIngredient(BaseModel):
    name: str
    quantity: str | None = None
    block: str | None = None


class RecipeStep(BaseModel):
    position: int
    title: str | None = None
    text: str


class RecipeCard(BaseModel):
    rank: int
    recipe_id: int
    title: str
    description: str | None = None
    calories_kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbs_g: float | None = None
    servings: int | None = None
    cooking_time: str | None = None
    difficulty: str | None = None
    allergens: list[str] = Field(default_factory=list)
    recipe_url: str
    similarity: float | None = None


class RecipeDetail(BaseModel):
    recipe_id: int
    title: str
    description: str | None = None
    ingredients: list[RecipeIngredient] = Field(default_factory=list)
    steps: list[RecipeStep] = Field(default_factory=list)
    nutrition: NutritionInfo = Field(default_factory=NutritionInfo)
    properties: dict[str, str | list[str] | None] = Field(default_factory=dict)
    servings: int | None = None
    recipe_url: str


class SourceInfo(BaseModel):
    type: str
    recipe_id: int | None = None
    title: str | None = None
    url: str | None = None


class SubstitutionOption(BaseModel):
    name: str
    ratio: str | None = None
    note: str | None = None
