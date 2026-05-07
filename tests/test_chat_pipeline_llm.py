from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.orchestrator.intent_router import IntentRouter
from app.orchestrator.pipeline import ChatPipeline
from app.schemas.chat import ChatRequest
from app.services.answer_generator import AnswerGenerator
from app.services.ingredient_catalog import IngredientCatalog
from app.services.llm.null import NullLLMClient
from app.services.substitution import SubstitutionService
from tests.evals.test_rag_scenarios import (
    InMemoryConversationStateService,
    InMemoryNutritionService,
    InMemoryRecipeRepository,
    InMemorySearchService,
    InMemoryVectorSearchService,
)


def _pipeline(*, include_llm: bool = False) -> ChatPipeline:
    settings = Settings.from_env()
    gen = AnswerGenerator(
        llm_client=NullLLMClient(),
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        num_ctx=settings.llm_num_ctx,
        think=settings.llm_think,
        llm_enabled=include_llm,
        answer_mode=settings.answer_mode,
        llm_postcheck_enabled=settings.llm_postcheck_enabled,
        llm_strict_context=settings.llm_strict_context,
        llm_max_answer_chars=settings.llm_max_answer_chars,
        llm_strip_think_tags=settings.llm_strip_think_tags,
        llm_log_prompts=settings.llm_log_prompts,
        llm_log_responses=settings.llm_log_responses,
        llm_min_recipes_for_list_answer=settings.llm_min_recipes_for_list_answer,
        llm_max_context_recipes=settings.llm_max_context_recipes,
        llm_max_context_ingredients=settings.llm_max_context_ingredients,
        llm_max_context_steps=settings.llm_max_context_steps,
    )
    return ChatPipeline(
        settings=settings,
        router=IntentRouter(),
        search_service=InMemorySearchService(),
        vector_search_service=InMemoryVectorSearchService(),
        recipe_repository=InMemoryRecipeRepository(),
        nutrition_service=InMemoryNutritionService(),
        substitution_service=SubstitutionService(IngredientCatalog.load()),
        conversation_state_service=InMemoryConversationStateService(),
        answer_generator=gen,
    )


def test_debug_llm_present_with_include_debug() -> None:
    pipeline = _pipeline()
    response = pipeline.handle_chat(
        ChatRequest(
            conversation_id="dbg",
            message="Какие есть рецепты с борщом без мяса?",
            options={"include_debug": True},
        )
    )
    assert response.debug is not None
    assert response.debug.llm is not None
    assert response.debug.llm["used_llm"] is False


def test_debug_llm_absent_without_include_debug() -> None:
    pipeline = _pipeline()
    response = pipeline.handle_chat(ChatRequest(conversation_id="dbg2", message="Какие есть рецепты с борщом?"))
    assert response.debug is None
