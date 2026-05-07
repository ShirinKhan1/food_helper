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
from app.services.llm.ollama import OllamaLLMClient
from app.services.substitution import SubstitutionService
from tests.evals.test_rag_scenarios import (
    InMemoryConversationStateService,
    InMemoryNutritionService,
    InMemoryRecipeRepository,
    InMemorySearchService,
    InMemoryVectorSearchService,
)


def _make_pipeline(answer_generator: AnswerGenerator) -> ChatPipeline:
    settings = Settings.from_env()
    return ChatPipeline(
        settings=settings,
        router=IntentRouter(),
        search_service=InMemorySearchService(),
        vector_search_service=InMemoryVectorSearchService(),
        recipe_repository=InMemoryRecipeRepository(),
        nutrition_service=InMemoryNutritionService(),
        substitution_service=SubstitutionService(IngredientCatalog.load()),
        conversation_state_service=InMemoryConversationStateService(),
        answer_generator=answer_generator,
    )


def test_pipeline_llm_disabled_matches_rule_based_answer() -> None:
    settings = Settings.from_env()
    ag = AnswerGenerator(
        llm_client=NullLLMClient(),
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        num_ctx=settings.llm_num_ctx,
        think=settings.llm_think,
        llm_enabled=settings.llm_enabled,
        answer_mode=settings.answer_mode,
        llm_postcheck_enabled=settings.llm_postcheck_enabled,
        llm_strict_context=settings.llm_strict_context,
        llm_max_answer_chars=settings.llm_max_answer_chars,
        llm_strip_think_tags=settings.llm_strip_think_tags,
    )
    pipeline = _make_pipeline(ag)
    response = pipeline.handle_chat(
        ChatRequest(conversation_id="c-llm-off", message="Какие есть рецепты с борщом без мяса?")
    )
    assert response.intent == "search_recipes"
    assert response.recipes
    assert "Постный борщ" in response.answer or "борщ" in response.answer.lower()


def test_pipeline_unreachable_ollama_falls_back_without_error() -> None:
    settings = Settings.from_env()
    ag = AnswerGenerator(
        llm_client=OllamaLLMClient(
            base_url="http://127.0.0.1:59134",
            model="qwen3:4b",
            timeout_seconds=0.5,
        ),
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        num_ctx=settings.llm_num_ctx,
        think=settings.llm_think,
        llm_enabled=True,
        answer_mode="llm",
        llm_postcheck_enabled=settings.llm_postcheck_enabled,
        llm_strict_context=settings.llm_strict_context,
        llm_max_answer_chars=settings.llm_max_answer_chars,
        llm_strip_think_tags=settings.llm_strip_think_tags,
    )
    pipeline = _make_pipeline(ag)
    response = pipeline.handle_chat(
        ChatRequest(conversation_id="c-llm-bad", message="Какие есть рецепты с борщом без мяса?")
    )
    assert response.intent == "search_recipes"
    assert response.recipes
    assert "Постный борщ" in response.answer or "Я нашел" in response.answer
