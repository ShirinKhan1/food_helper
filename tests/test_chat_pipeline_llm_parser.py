from __future__ import annotations

from dataclasses import replace

from app.core.config import Settings
from app.orchestrator.clarification import ClarificationManager
from app.orchestrator.intent_router import IntentRouter
from app.orchestrator.parsed_request_adapter import ParsedRequestAdapter
from app.orchestrator.pipeline import ChatPipeline
from app.schemas.chat import ChatRequest
from app.services.answer_generator import AnswerGenerator
from app.services.ingredient_catalog import IngredientCatalog
from app.services.llm.null import NullLLMClient
from app.services.llm.parser_postcheck import ParserPostcheck
from app.services.llm.query_parser import LLMQueryParser
from app.services.substitution import SubstitutionService
from tests.evals.test_rag_scenarios import (
    InMemoryConversationStateService,
    InMemoryNutritionService,
    InMemoryRecipeRepository,
    InMemorySearchService,
    InMemoryVectorSearchService,
)
from tests.test_llm_answer_generator import FakeSuccessLLM


def _pipeline(settings: Settings) -> ChatPipeline:
    ag = AnswerGenerator(
        llm_client=NullLLMClient(),
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        num_ctx=settings.llm_num_ctx,
        think=settings.llm_think,
        llm_enabled=False,
        answer_mode="template",
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
        answer_generator=ag,
        query_parser=LLMQueryParser(settings=settings, llm_client=None, postcheck=ParserPostcheck()),
        parsed_request_adapter=ParsedRequestAdapter(settings=settings),
        clarification_manager=ClarificationManager(),
    )


def test_rules_mode_same_as_before_search() -> None:
    base = Settings.from_env()
    settings = replace(base, query_parser_mode="rules", llm_query_parser_enabled=False)
    pipeline = _pipeline(settings)
    r = pipeline.handle_chat(ChatRequest(conversation_id="p1", message="Найди рецепты с курицей."))
    assert r.intent == "search_recipes"
    assert r.route == "hybrid_search"
    assert r.requires_clarification is False


def test_include_debug_has_parser_section() -> None:
    base = Settings.from_env()
    settings = replace(base, query_parser_mode="rules", llm_query_parser_enabled=False)
    pipeline = _pipeline(settings)
    r = pipeline.handle_chat(
        ChatRequest(
            conversation_id="p2",
            message="Найди рецепты с курицей.",
            options={"include_debug": True},
        )
    )
    assert r.debug is not None
    assert r.debug.parser is not None
    assert r.debug.parser.get("mode") == "rules"
    assert r.debug.parser.get("used_llm") is False


def test_llm_invalid_json_no_500() -> None:
    base = Settings.from_env()
    settings = replace(
        base,
        query_parser_mode="llm",
        llm_query_parser_enabled=True,
        llm_query_parser_postcheck_enabled=True,
    )
    ag = AnswerGenerator(
        llm_client=FakeSuccessLLM("not-json"),
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        num_ctx=settings.llm_num_ctx,
        think=settings.llm_think,
        llm_enabled=True,
        answer_mode="llm",
        llm_postcheck_enabled=False,
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
    pipeline = ChatPipeline(
        settings=settings,
        router=IntentRouter(),
        search_service=InMemorySearchService(),
        vector_search_service=InMemoryVectorSearchService(),
        recipe_repository=InMemoryRecipeRepository(),
        nutrition_service=InMemoryNutritionService(),
        substitution_service=SubstitutionService(IngredientCatalog.load()),
        conversation_state_service=InMemoryConversationStateService(),
        answer_generator=ag,
        query_parser=LLMQueryParser(
            settings=settings,
            llm_client=FakeSuccessLLM("not-json"),
            postcheck=ParserPostcheck(),
        ),
        parsed_request_adapter=ParsedRequestAdapter(settings=settings),
        clarification_manager=ClarificationManager(),
    )
    r = pipeline.handle_chat(ChatRequest(conversation_id="p3", message="Найди рецепты с борщом без мяса."))
    assert r.intent == "search_recipes"
    assert r.recipes
