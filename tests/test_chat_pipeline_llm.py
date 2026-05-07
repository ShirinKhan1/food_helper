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
from app.services.conversation_state import ConversationSnapshot
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
from tests.test_llm_answer_generator import FakeSuccessLLM


def _answer_generator_from_settings(
    settings: Settings,
    *,
    llm_client,
    llm_enabled: bool,
    answer_mode: str | None = None,
    llm_postcheck_enabled: bool | None = None,
) -> AnswerGenerator:
    return AnswerGenerator(
        llm_client=llm_client,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        num_ctx=settings.llm_num_ctx,
        think=settings.llm_think,
        llm_enabled=llm_enabled,
        answer_mode=answer_mode if answer_mode is not None else settings.answer_mode,
        llm_postcheck_enabled=(
            llm_postcheck_enabled if llm_postcheck_enabled is not None else settings.llm_postcheck_enabled
        ),
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


def _chat_pipeline(
    answer_generator: AnswerGenerator,
    *,
    conversation_state: InMemoryConversationStateService | None = None,
) -> ChatPipeline:
    settings = Settings.from_env()
    conv = conversation_state or InMemoryConversationStateService()
    return ChatPipeline(
        settings=settings,
        router=IntentRouter(),
        search_service=InMemorySearchService(),
        vector_search_service=InMemoryVectorSearchService(),
        recipe_repository=InMemoryRecipeRepository(),
        nutrition_service=InMemoryNutritionService(),
        substitution_service=SubstitutionService(IngredientCatalog.load()),
        conversation_state_service=conv,
        answer_generator=answer_generator,
    )


def _pipeline(
    *,
    include_llm: bool = False,
    answer_generator: AnswerGenerator | None = None,
    conversation_state: InMemoryConversationStateService | None = None,
) -> ChatPipeline:
    settings = Settings.from_env()
    if answer_generator is not None:
        gen = answer_generator
    else:
        gen = _answer_generator_from_settings(settings, llm_client=NullLLMClient(), llm_enabled=include_llm)
    return _chat_pipeline(gen, conversation_state=conversation_state)


def _pipeline_fake_llm(
    response: str = "LLM ответ",
    *,
    conversation_state: InMemoryConversationStateService | None = None,
) -> ChatPipeline:
    settings = Settings.from_env()
    gen = _answer_generator_from_settings(
        settings,
        llm_client=FakeSuccessLLM(response),
        llm_enabled=True,
        answer_mode="llm",
        llm_postcheck_enabled=False,
    )
    return _chat_pipeline(gen, conversation_state=conversation_state)


def _assert_debug_llm_fields(llm_debug: dict) -> None:
    assert set(llm_debug.keys()) >= {"used_llm", "fallback_reason", "postcheck_passed", "postcheck_errors"}


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


def test_debug_llm_search_with_fake_llm() -> None:
    pipeline = _pipeline_fake_llm("Поиск LLM")
    response = pipeline.handle_chat(
        ChatRequest(
            conversation_id="dbg-search",
            message="Какие есть рецепты с борщом без мяса?",
            options={"include_debug": True},
        )
    )
    assert response.debug is not None and response.debug.llm is not None
    _assert_debug_llm_fields(response.debug.llm)
    assert response.debug.llm["used_llm"] is True
    assert response.debug.llm["fallback_reason"] is None
    assert response.debug.llm["postcheck_passed"] is None
    assert response.debug.llm["postcheck_errors"] == []
    assert response.answer == "Поиск LLM"


def test_debug_llm_recipe_details_with_fake_llm() -> None:
    conv = InMemoryConversationStateService()
    conv.snapshots["dbg-det"] = ConversationSnapshot(conversation_id="dbg-det", last_recipe_results=[1, 2, 3])
    pipeline = _pipeline_fake_llm("Детали LLM", conversation_state=conv)
    response = pipeline.handle_chat(
        ChatRequest(
            conversation_id="dbg-det",
            message="Покажи второй рецепт.",
            options={"include_debug": True},
        )
    )
    assert response.intent == "recipe_details"
    assert response.debug is not None and response.debug.llm is not None
    _assert_debug_llm_fields(response.debug.llm)
    assert response.debug.llm["used_llm"] is True
    assert response.answer == "Детали LLM"


def test_debug_llm_nutrition_with_fake_llm() -> None:
    pipeline = _pipeline_fake_llm("БЖУ LLM")
    response = pipeline.handle_chat(
        ChatRequest(
            conversation_id="dbg-nut",
            message="Сколько калорий в яблочном пироге?",
            options={"include_debug": True},
        )
    )
    assert response.intent == "nutrition_question"
    assert response.debug is not None and response.debug.llm is not None
    _assert_debug_llm_fields(response.debug.llm)
    assert response.debug.llm["used_llm"] is True
    assert response.answer == "БЖУ LLM"


def test_debug_llm_ingredient_substitution_with_fake_llm() -> None:
    conv = InMemoryConversationStateService()
    conv.snapshots["dbg-sub"] = ConversationSnapshot(conversation_id="dbg-sub", last_recipe_results=[1, 2, 3])
    pipeline = _pipeline_fake_llm("Замена LLM", conversation_state=conv)
    response = pipeline.handle_chat(
        ChatRequest(
            conversation_id="dbg-sub",
            message="На что в третьем рецепте можно заменить сахар?",
            options={"include_debug": True},
        )
    )
    assert response.intent == "ingredient_substitution"
    assert response.debug is not None and response.debug.llm is not None
    _assert_debug_llm_fields(response.debug.llm)
    assert response.debug.llm["used_llm"] is True
    assert response.answer == "Замена LLM"


def test_debug_llm_general_substitution_with_fake_llm() -> None:
    pipeline = _pipeline_fake_llm("Общая замена LLM")
    response = pipeline.handle_chat(
        ChatRequest(
            conversation_id="dbg-gen-sub",
            message="На что заменить сахар?",
            options={"include_debug": True},
        )
    )
    assert response.intent == "general_substitution"
    assert response.debug is not None and response.debug.llm is not None
    _assert_debug_llm_fields(response.debug.llm)
    assert response.debug.llm["used_llm"] is True
    assert response.answer == "Общая замена LLM"
