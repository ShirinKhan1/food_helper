from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.recipe import RecipeCard


class EventProfile(BaseModel):
    event_type: str | None = None
    guests_count: int | None = None
    format: str | None = None
    vibe: list[str] = Field(default_factory=list)
    meal_roles: list[str] = Field(default_factory=list)
    preparation_style: str | None = None


class EventMenuGroup(BaseModel):
    role: str
    title: str
    recipes: list[RecipeCard] = Field(default_factory=list)
