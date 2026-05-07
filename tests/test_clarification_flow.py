from __future__ import annotations

from dataclasses import replace

from app.core.config import Settings
from app.orchestrator.clarification import ClarificationManager, PendingClarification
from app.schemas.parser import ClarificationRequest, ParsedQueryConstraints, ParsedUserRequest
from app.services.conversation_state import ConversationSnapshot


def test_build_pending_roundtrip() -> None:
    mgr = ClarificationManager()
    parsed = ParsedUserRequest(
        intent="recommend_recipes",
        confidence=0.8,
        requires_clarification=True,
        clarification=ClarificationRequest(
            reason="ambiguous_light_goal",
            question="Легкое по калориям или в приготовлении?",
            expected_fields=["diet_goal"],
            options=["по калориям", "в приготовлении"],
        ),
        constraints=ParsedQueryConstraints(),
    )
    p = mgr.build_pending(original_message="легкое", parsed=parsed)
    assert isinstance(p, PendingClarification)
    assert p.reason == "ambiguous_light_goal"


def test_try_resolve_merge_prep() -> None:
    mgr = ClarificationManager()
    partial = ParsedUserRequest(
        intent="recommend_recipes",
        confidence=0.8,
        constraints=ParsedQueryConstraints(),
    )
    pending = PendingClarification(
        original_message="легкое",
        partial_parsed_request=partial.model_dump(mode="json"),
        question="?",
        expected_fields=[],
        options=["по калориям", "в приготовлении"],
        created_at="2026-01-01T00:00:00Z",
        reason="ambiguous_light_goal",
    )
    snap = ConversationSnapshot(conversation_id="c")
    r = mgr.try_resolve(pending=pending, message="в приготовлении", snapshot=snap)
    assert r.resolved and r.parsed is not None
    assert r.parsed.constraints.max_cooking_time_minutes == 30


def test_try_resolve_new_query_abandons() -> None:
    mgr = ClarificationManager()
    partial = ParsedUserRequest(
        intent="recommend_recipes",
        confidence=0.8,
        constraints=ParsedQueryConstraints(),
    )
    pending = PendingClarification(
        original_message="легкое",
        partial_parsed_request=partial.model_dump(mode="json"),
        question="?",
        expected_fields=[],
        options=[],
        created_at="2026-01-01T00:00:00Z",
        reason="ambiguous_light_goal",
    )
    snap = ConversationSnapshot(conversation_id="c")
    r = mgr.try_resolve(
        pending=pending,
        message="Найди рецепты борща без мяса",
        snapshot=snap,
    )
    assert r.abandon_pending


def test_clarification_disabled_via_settings_no_crash() -> None:
    from app.orchestrator.intent_router import IntentRouter
    from app.orchestrator.parsed_request_adapter import ParsedRequestAdapter
    from app.orchestrator.pipeline import ChatPipeline
    from app.schemas.chat import ChatRequest
    from app.services.answer_generator import AnswerGenerator
    from app.services.llm.null import NullLLMClient
    from app.services.llm.parser_postcheck import ParserPostcheck
    from app.services.llm.query_parser import LLMQueryParser
    from app.services.ingredient_catalog import IngredientCatalog
    from app.services.substitution import SubstitutionService
    from tests.evals.test_rag_scenarios import (
        InMemoryConversationStateService,
        InMemoryNutritionService,
        InMemoryRecipeRepository,
        InMemorySearchService,
        InMemoryVectorSearchService,
    )

    settings = replace(Settings.from_env(), clarification_enabled=False)
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
    conv = InMemoryConversationStateService()
    conv.set_pending_clarification(
        "c1",
        ClarificationManager().build_pending(
            original_message="x",
            parsed=ParsedUserRequest(
                intent="recommend_recipes",
                confidence=0.9,
                requires_clarification=True,
                clarification=ClarificationRequest(reason="t", question="q?", expected_fields=[], options=[]),
                constraints=ParsedQueryConstraints(),
            ),
        ),
    )
    pipeline = ChatPipeline(
        settings=settings,
        router=IntentRouter(),
        search_service=InMemorySearchService(),
        vector_search_service=InMemoryVectorSearchService(),
        recipe_repository=InMemoryRecipeRepository(),
        nutrition_service=InMemoryNutritionService(),
        substitution_service=SubstitutionService(IngredientCatalog.load()),
        conversation_state_service=conv,
        answer_generator=ag,
        query_parser=LLMQueryParser(
            settings=settings,
            llm_client=None,
            postcheck=ParserPostcheck(),
        ),
        parsed_request_adapter=ParsedRequestAdapter(settings=settings),
        clarification_manager=ClarificationManager(),
    )
    r = pipeline.handle_chat(ChatRequest(conversation_id="c1", message="ответ"))
    assert r.requires_clarification is False
