from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.event import EventMenuGroup, EventProfile
from app.schemas.parser import ClarificationRequest
from app.schemas.recipe import NutritionInfo, RecipeCard, RecipeDetail, SourceInfo, SubstitutionOption
from app.schemas.search import QueryConstraints


class ChatOptions(BaseModel):
    top_k: int = 5
    include_debug: bool = False


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    options: ChatOptions = Field(default_factory=ChatOptions)
    edit_user_message_id: int | None = None


class IntentDecision(BaseModel):
    intent: Literal[
        "search_recipes",
        "recommend_recipes",
        "event_recommendation",
        "nutrition_question",
        "ingredient_substitution",
        "general_substitution",
        "recipe_details",
        "similar_recipes",
        "allergy_or_exclusion",
        "conversation_recall",
        "fallback",
    ]
    route: Literal[
        "no_retrieval",
        "sql",
        "vector_search",
        "hybrid_search",
        "event_menu_recommendation",
        "conversation_recipe_fetch",
        "conversation_history",
        "substitution",
        "substitution_catalog",
        "clarification",
    ]
    entities: dict = Field(default_factory=dict)
    needs_conversation_context: bool = False
    needs_recipe_fetch: bool = False
    needs_vector_search: bool = False
    needs_sql: bool = False
    needs_llm: bool = False


class ChatDebugInfo(BaseModel):
    normalized_query: str | None = None
    constraints: QueryConstraints = Field(default_factory=QueryConstraints)
    intent_decision: IntentDecision | None = None
    vector_results: list[dict] = Field(default_factory=list)
    keyword_results: list[dict] = Field(default_factory=list)
    final_results: list[dict] = Field(default_factory=list)
    event_recommendation: dict | None = None
    llm: dict | None = None
    parser: dict | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    intent: str
    route: str
    recipes: list[RecipeCard] = Field(default_factory=list)
    event_profile: EventProfile | None = None
    event_menu: list[EventMenuGroup] = Field(default_factory=list)
    selected_recipe: RecipeDetail | None = None
    nutrition: NutritionInfo | None = None
    substitutions: list[SubstitutionOption] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sources: list[SourceInfo] = Field(default_factory=list)
    debug: ChatDebugInfo | None = None
    requires_clarification: bool = False
    clarification: ClarificationRequest | None = None
    user_message_id: int | None = None
    assistant_message_id: int | None = None
