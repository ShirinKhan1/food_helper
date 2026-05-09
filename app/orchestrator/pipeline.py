from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID
import logging
import re

LOGGER = logging.getLogger(__name__)

from app.core.config import Settings
from app.orchestrator.clarification import ClarificationManager, PendingClarification
from app.orchestrator.dialog_follow_up import apply_follow_up_context
from app.orchestrator.intent_router import IntentRouter
from app.orchestrator.parsed_request_adapter import ParsedRequestAdapter
from app.orchestrator.query_constraints import extract_query_constraints
from app.orchestrator.event_extractor import extract_event_profile
from app.schemas.event import EventMenuGroup, EventProfile
from app.schemas.chat import ChatDebugInfo, ChatOptions, ChatRequest, ChatResponse, IntentDecision
from app.schemas.parser import ClarificationRequest, ParsedUserRequest
from app.schemas.recipe import NutritionInfo, RecipeCard, RecipeDetail, SourceInfo, SubstitutionOption
from app.schemas.search import QueryConstraints
from app.services.event_ranker import EventRanker
from app.services.event_search_query import build_event_search_query
from app.services.menu_composer import MenuComposer
from app.services.conversation_state import ConversationStateService
from app.services.answer_generator import AnswerGenerator
from app.services.llm.query_parser import LLMQueryParser
from app.services.llm.result import AnswerGenerationResult
from app.services.nutrition import NutritionService
from app.services.recipe_repository import RecipeRepository
from app.services.search_service import SearchService
from app.services.substitution import SubstitutionService
from app.services.vector_search import VectorSearchService

ALLERGY_WARNING = (
    "Проверьте состав конкретных продуктов и возможные следы аллергенов на упаковке. "
    "Я могу отфильтровать рецепты по данным из базы, но не могу гарантировать медицинскую безопасность блюда."
)


@dataclass
class ResolvedRecipe:
    row: dict | None
    candidates: list[dict]


class ChatPipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        router: IntentRouter,
        search_service: SearchService,
        vector_search_service: VectorSearchService,
        recipe_repository: RecipeRepository,
        nutrition_service: NutritionService,
        substitution_service: SubstitutionService,
        conversation_state_service: ConversationStateService,
        answer_generator: AnswerGenerator,
        query_parser: LLMQueryParser,
        parsed_request_adapter: ParsedRequestAdapter,
        clarification_manager: ClarificationManager,
    ) -> None:
        self._settings = settings
        self._router = router
        self._search_service = search_service
        self._vector_search_service = vector_search_service
        self._recipe_repository = recipe_repository
        self._nutrition_service = nutrition_service
        self._substitution_service = substitution_service
        self._conversation_state_service = conversation_state_service
        self._answer_generator = answer_generator
        self._query_parser = query_parser
        self._parsed_request_adapter = parsed_request_adapter
        self._clarification_manager = clarification_manager
        self._event_ranker = EventRanker()
        self._menu_composer = MenuComposer()

    def _chat_debug_log(self, options: ChatOptions, msg: str, *args: object) -> None:
        if options.include_debug:
            LOGGER.info("[chat debug] " + msg, *args)

    def _chat_debug_search(self, options: ChatOptions, label: str, execution: object) -> None:
        if not options.include_debug:
            return
        LOGGER.info(
            "[chat debug] %s hits final=%d vector=%d keyword=%d normalized_query=%r",
            label,
            len(getattr(execution, "final_results", ()) or ()),
            len(getattr(execution, "vector_results", ()) or ()),
            len(getattr(execution, "keyword_results", ()) or ()),
            getattr(execution, "normalized_query", None),
        )

    def _chat_debug_llm(self, options: ChatOptions, llm_result: AnswerGenerationResult | None) -> None:
        if not options.include_debug or llm_result is None:
            return
        LOGGER.info(
            "[chat debug] answer_llm used=%s fallback=%s latency_ms=%s postcheck=%s",
            llm_result.used_llm,
            llm_result.fallback_reason,
            llm_result.latency_ms,
            llm_result.postcheck_passed,
        )

    def _append_assistant_with_snapshot(self, conversation_id: str, content: str) -> int:
        snap = self._conversation_state_service.export_state_json(conversation_id)
        return self._conversation_state_service.append_message(
            conversation_id,
            role="assistant",
            content=content,
            state_after_turn=snap,
        )

    def handle_chat(self, request: ChatRequest, *, current_user_id: UUID | None = None) -> ChatResponse:
        conversation_id = self._conversation_state_service.prepare_conversation(
            request.conversation_id,
            current_user_id,
        )
        if request.edit_user_message_id is not None:
            self._conversation_state_service.fork_at_user_message(
                conversation_id,
                request.edit_user_message_id,
            )
        user_message_id = self._conversation_state_service.append_message(
            conversation_id,
            role="user",
            content=request.message,
        )
        self._chat_debug_log(
            request.options,
            "request start conv=%s client_conv=%r message_chars=%d top_k=%d",
            conversation_id,
            request.conversation_id,
            len(request.message),
            request.options.top_k,
        )

        snapshot = self._conversation_state_service.get_snapshot(conversation_id)
        if snapshot.pending_clarification and not self._settings.clarification_enabled:
            self._conversation_state_service.clear_pending_clarification(conversation_id)
            snapshot = self._conversation_state_service.get_snapshot(conversation_id)
        recent_messages = self._conversation_state_service.get_recent_messages(
            conversation_id,
            limit=self._settings.query_parser_recent_messages_limit,
        )

        parser_result = None
        pre_resolved_parsed: ParsedUserRequest | None = None
        pending = snapshot.pending_clarification
        if pending and self._settings.clarification_enabled:
            resolved = self._clarification_manager.try_resolve(
                pending=pending,
                message=request.message,
                snapshot=snapshot,
            )
            if resolved.should_repeat_question:
                self._chat_debug_log(request.options, "branch repeat pending clarification question")
                clar = self._pending_to_clarification_request(pending)
                response = ChatResponse(
                    conversation_id=conversation_id,
                    answer=pending.question,
                    intent="clarification_required",
                    route="clarification",
                    requires_clarification=True,
                    clarification=clar,
                    debug=self._build_debug(
                        options=request.options,
                        constraints=extract_query_constraints(request.message),
                        decision=self._router.decide(request.message),
                        parser_debug=self._parser_debug_dict(parser_result),
                    ),
                    user_message_id=user_message_id,
                )
                assistant_message_id = self._append_assistant_with_snapshot(
                    conversation_id,
                    response.answer,
                )
                return response.model_copy(update={"assistant_message_id": assistant_message_id})
            if resolved.abandon_pending:
                self._conversation_state_service.clear_pending_clarification(conversation_id)
            if resolved.resolved and resolved.parsed is not None:
                pre_resolved_parsed = resolved.parsed

        rule_constraints = extract_query_constraints(request.message)
        rule_decision = self._router.decide(request.message)

        if pre_resolved_parsed is None:
            parser_result = self._query_parser.parse(
                message=request.message,
                rule_decision=rule_decision,
                rule_constraints=rule_constraints,
                recent_messages=recent_messages,
                conversation_snapshot=self._conversation_state_service.get_snapshot(conversation_id),
            )
            parsed = parser_result.parsed
        else:
            parsed = pre_resolved_parsed

        if request.options.include_debug:
            if parser_result is not None:
                self._chat_debug_log(
                    request.options,
                    "parser mode=%s used_llm=%s latency_ms=%s intent=%s confidence=%s postcheck=%s",
                    self._settings.query_parser_mode,
                    parser_result.used_llm,
                    parser_result.latency_ms,
                    parsed.intent,
                    parsed.confidence,
                    parser_result.postcheck_passed,
                )
            else:
                self._chat_debug_log(
                    request.options,
                    "parser skipped (pending clarification resolved) intent=%s confidence=%s",
                    parsed.intent,
                    parsed.confidence,
                )

        if not self._settings.clarification_enabled:
            parsed = parsed.model_copy(update={"requires_clarification": False, "clarification": None})

        if parsed.requires_clarification and parsed.clarification is not None:
            self._chat_debug_log(request.options, "emit clarification_required intent=%s", parsed.intent)
            pending_obj = self._clarification_manager.build_pending(
                original_message=request.message,
                parsed=parsed,
            )
            self._conversation_state_service.set_pending_clarification(conversation_id, pending_obj)
            clar = parsed.clarification
            response = ChatResponse(
                conversation_id=conversation_id,
                answer=clar.question,
                intent="clarification_required",
                route="clarification",
                requires_clarification=True,
                clarification=clar,
                debug=self._build_debug(
                    options=request.options,
                    constraints=rule_constraints,
                    decision=rule_decision,
                    parser_debug=self._parser_debug_dict(parser_result),
                ),
                user_message_id=user_message_id,
            )
            assistant_message_id = self._append_assistant_with_snapshot(
                conversation_id,
                response.answer,
            )
            return response.model_copy(update={"assistant_message_id": assistant_message_id})

        decision, constraints, message_for_search = self._parsed_request_adapter.to_pipeline_inputs(
            parsed=parsed,
            rule_decision=rule_decision,
            rule_constraints=rule_constraints,
            message=request.message,
        )
        snapshot = self._conversation_state_service.get_snapshot(conversation_id)
        decision, constraints, message_for_search, exclude_ids, clear_last_event_profile = (
            apply_follow_up_context(
                message=request.message,
                snapshot=snapshot,
                decision=decision,
                constraints=constraints,
                message_for_search=message_for_search,
                event_recommendation_enabled=self._settings.event_recommendation_enabled,
            )
        )
        if clear_last_event_profile:
            self._conversation_state_service.update_snapshot(conversation_id, last_event_profile=None)
        recent_dialog = self._recent_dialog_payload(recent_messages)
        warnings = self._warnings_from_constraints(constraints)
        self._chat_debug_log(
            request.options,
            "dispatch inputs intent=%s route=%s search_message_chars=%d "
            "constraints dish=%r include=%d exclude=%d allergies=%d",
            decision.intent,
            decision.route,
            len(message_for_search),
            constraints.dish,
            len(constraints.include_ingredients),
            len(constraints.exclude_ingredients),
            len(constraints.allergy_exclusions),
        )
        response = self._dispatch(
            conversation_id=conversation_id,
            message=message_for_search,
            options=request.options,
            constraints=constraints,
            decision=decision,
            warnings=warnings,
            parser_debug=self._parser_debug_dict(parser_result),
            exclude_recipe_ids=exclude_ids,
            recent_dialog=recent_dialog,
        )
        self._conversation_state_service.clear_pending_clarification(conversation_id)
        assistant_message_id = self._append_assistant_with_snapshot(
            conversation_id,
            response.answer,
        )
        self._chat_debug_log(
            request.options,
            "done intent=%s route=%s answer_chars=%d recipes=%d",
            response.intent,
            response.route,
            len(response.answer),
            len(response.recipes),
        )
        return response.model_copy(
            update={
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
            },
        )

    def _pending_to_clarification_request(self, pending: PendingClarification) -> ClarificationRequest:
        return ClarificationRequest(
            reason=pending.reason or "unknown",
            question=pending.question,
            expected_fields=pending.expected_fields,
            options=pending.options,
        )

    def _recent_dialog_payload(self, recent_messages: list[tuple[str, str]]) -> list[dict[str, str]]:
        limit = self._settings.query_parser_recent_messages_limit
        cap = 500
        out: list[dict[str, str]] = []
        for role, content in recent_messages[-limit:]:
            text = (content or "").strip()
            if len(text) > cap:
                text = text[: cap - 1] + "…"
            out.append({"role": role, "content": text})
        return out

    def _parser_debug_dict(self, parser_result) -> dict | None:
        if parser_result is None:
            return None
        parsed = parser_result.parsed
        safe_parsed = {
            "intent": parsed.intent,
            "confidence": parsed.confidence,
            "requires_clarification": parsed.requires_clarification,
            "constraints": parsed.constraints.model_dump(),
            "event_profile": parsed.event_profile.model_dump(mode="json", exclude_none=True)
            if parsed.event_profile
            else None,
        }
        return {
            "mode": self._settings.query_parser_mode,
            "used_llm": parser_result.used_llm,
            "fallback_reason": parser_result.fallback_reason,
            "latency_ms": parser_result.latency_ms,
            "postcheck_passed": parser_result.postcheck_passed,
            "postcheck_errors": list(parser_result.postcheck_errors),
            "parsed_request": safe_parsed,
        }

    def _dispatch(
        self,
        *,
        conversation_id: str,
        message: str,
        options: ChatOptions,
        constraints: QueryConstraints,
        decision: IntentDecision,
        warnings: list[str],
        parser_debug: dict | None = None,
        exclude_recipe_ids: frozenset[int] | None = None,
        recent_dialog: list[dict[str, str]] | None = None,
    ) -> ChatResponse:
        self._chat_debug_log(
            options,
            "_dispatch intent=%s route=%s",
            decision.intent,
            decision.route,
        )
        if decision.intent == "event_recommendation":
            return self._dispatch_event_recommendation(
                conversation_id=conversation_id,
                message=message,
                options=options,
                constraints=constraints,
                decision=decision,
                warnings=warnings,
                parser_debug=parser_debug,
                exclude_recipe_ids=exclude_recipe_ids,
                recent_dialog=recent_dialog,
            )

        if decision.intent in {"search_recipes", "recommend_recipes", "allergy_or_exclusion"}:
            execution = self._search_service.search(
                message,
                constraints=constraints,
                top_k=options.top_k,
                exclude_recipe_ids=exclude_recipe_ids,
            )
            self._chat_debug_search(options, "recipe search", execution)
            recipes = self._rows_to_cards(execution.final_results)
            self._conversation_state_service.update_snapshot(
                conversation_id,
                last_recipe_results=[card.recipe_id for card in recipes],
                selected_recipe_id=None,
                last_event_profile=None,
            )
            fallback_answer = self._render_recipe_list_answer(decision.intent, recipes)
            llm_result = self._answer_generator.generate_recipe_list_answer(
                intent=decision.intent,
                user_message=message,
                fallback_answer=fallback_answer,
                recipes=recipes,
                warnings=warnings,
                constraints=constraints,
                sources=self._sources_from_cards(recipes),
                recent_dialog=recent_dialog,
            )
            self._chat_debug_llm(options, llm_result)
            return ChatResponse(
                conversation_id=conversation_id,
                answer=llm_result.answer,
                intent=decision.intent,
                route=decision.route,
                recipes=recipes,
                warnings=warnings,
                sources=self._sources_from_cards(recipes),
                debug=self._build_debug(
                    options=options,
                    constraints=constraints,
                    decision=decision,
                    execution=execution,
                    llm_result=llm_result,
                    parser_debug=parser_debug,
                ),
            )

        if decision.intent == "nutrition_question":
            resolved = self._resolve_recipe(conversation_id, decision)
            if resolved.row is None:
                if not resolved.candidates and self._should_search_candidates_for_nutrition(decision, constraints):
                    execution = self._search_service.search(
                        message,
                        constraints=constraints,
                        top_k=options.top_k,
                        exclude_recipe_ids=exclude_recipe_ids,
                    )
                    self._chat_debug_search(options, "nutrition candidate search", execution)
                    recipes = self._rows_to_cards(execution.final_results)
                    self._conversation_state_service.update_snapshot(
                        conversation_id,
                        last_recipe_results=[card.recipe_id for card in recipes],
                        selected_recipe_id=None,
                    )
                    fallback_answer = self._render_nutrition_candidate_answer(
                        recipes,
                        nutrients=decision.entities.get("nutrients") or [decision.entities.get("nutrient")],
                    )
                    llm_result = self._answer_generator.generate_nutrition_candidates_answer(
                        intent=decision.intent,
                        user_message=message,
                        fallback_answer=fallback_answer,
                        recipes=recipes,
                        warnings=warnings,
                        constraints=constraints,
                        sources=self._sources_from_cards(recipes),
                        recent_dialog=recent_dialog,
                    )
                    self._chat_debug_llm(options, llm_result)
                    return ChatResponse(
                        conversation_id=conversation_id,
                        answer=llm_result.answer,
                        intent=decision.intent,
                        route="hybrid_search",
                        recipes=recipes,
                        warnings=warnings,
                        sources=self._sources_from_cards(recipes),
                        debug=self._build_debug(
                            options=options,
                            constraints=constraints,
                            decision=decision,
                            execution=execution,
                            llm_result=llm_result,
                            parser_debug=parser_debug,
                        ),
                    )
                return self._response_for_missing_recipe(
                    conversation_id=conversation_id,
                    decision=decision,
                    warnings=warnings,
                    candidates=resolved.candidates,
                    answer_if_missing="Я не смог однозначно определить рецепт. Напишите его название или сначала попросите найти рецепты.",
                    options=options,
                    constraints=constraints,
                    parser_debug=parser_debug,
                )
            detail = self._recipe_repository.row_to_recipe_detail(resolved.row)
            nutrient = decision.entities.get("nutrient")
            nutrition = self._nutrition_service.get_nutrition(detail.recipe_id) or detail.nutrition
            fallback_answer = self._nutrition_service.format_answer(detail.title, nutrition, nutrient)
            llm_result = self._answer_generator.generate_nutrition_answer(
                user_message=message,
                fallback_answer=fallback_answer,
                nutrition=nutrition,
                detail=detail,
                warnings=warnings,
                constraints=constraints,
                sources=[self._source_from_detail(detail)],
                recent_dialog=recent_dialog,
            )
            self._chat_debug_llm(options, llm_result)
            self._conversation_state_service.update_snapshot(
                conversation_id,
                selected_recipe_id=detail.recipe_id,
            )
            return ChatResponse(
                conversation_id=conversation_id,
                answer=llm_result.answer,
                intent=decision.intent,
                route=decision.route,
                selected_recipe=detail,
                nutrition=nutrition,
                warnings=warnings,
                sources=[self._source_from_detail(detail)],
                debug=self._build_debug(
                    options=options,
                    constraints=constraints,
                    decision=decision,
                    llm_result=llm_result,
                    parser_debug=parser_debug,
                ),
            )

        if decision.intent == "recipe_details":
            resolved = self._resolve_recipe(conversation_id, decision)
            if resolved.row is None:
                return self._response_for_missing_recipe(
                    conversation_id=conversation_id,
                    decision=decision,
                    warnings=warnings,
                    candidates=resolved.candidates,
                    answer_if_missing="Я пока не показывал список рецептов в этом диалоге. Напишите, какой рецепт найти, или задайте поиск.",
                    options=options,
                    constraints=constraints,
                    parser_debug=parser_debug,
                )
            detail = self._recipe_repository.row_to_recipe_detail(resolved.row)
            self._conversation_state_service.update_snapshot(
                conversation_id,
                selected_recipe_id=detail.recipe_id,
            )
            fallback_answer = self._render_recipe_detail_answer(message, detail)
            llm_result = self._answer_generator.generate_recipe_detail_answer(
                user_message=message,
                fallback_answer=fallback_answer,
                detail=detail,
                warnings=warnings,
                constraints=constraints,
                sources=[self._source_from_detail(detail)],
                recent_dialog=recent_dialog,
            )
            self._chat_debug_llm(options, llm_result)
            return ChatResponse(
                conversation_id=conversation_id,
                answer=llm_result.answer,
                intent=decision.intent,
                route=decision.route,
                selected_recipe=detail,
                warnings=warnings,
                sources=[self._source_from_detail(detail)],
                debug=self._build_debug(
                    options=options,
                    constraints=constraints,
                    decision=decision,
                    llm_result=llm_result,
                    parser_debug=parser_debug,
                ),
            )

        if decision.intent == "general_substitution":
            target = str(decision.entities.get("target_ingredient") or "ингредиент")
            substitution = self._substitution_service.suggest_general(target)
            warnings = [*warnings, *substitution.warnings]
            fallback_answer = self._render_general_substitutions_answer(target, substitution.options)
            llm_result = self._answer_generator.generate_general_substitution_answer(
                user_message=message,
                fallback_answer=fallback_answer,
                substitutions=substitution.options,
                warnings=warnings,
                constraints=constraints,
                recent_dialog=recent_dialog,
            )
            self._chat_debug_llm(options, llm_result)
            return ChatResponse(
                conversation_id=conversation_id,
                answer=llm_result.answer,
                intent=decision.intent,
                route=decision.route,
                substitutions=substitution.options,
                warnings=warnings,
                debug=self._build_debug(
                    options=options,
                    constraints=constraints,
                    decision=decision,
                    llm_result=llm_result,
                    parser_debug=parser_debug,
                ),
            )

        if decision.intent == "ingredient_substitution":
            resolved = self._resolve_recipe(conversation_id, decision)
            if resolved.row is None:
                target = decision.entities.get("target_ingredient")
                if target and not resolved.candidates:
                    substitution = self._substitution_service.suggest_general(str(target))
                    warnings = [*warnings, *substitution.warnings]
                    return ChatResponse(
                        conversation_id=conversation_id,
                        answer=self._render_general_substitutions_answer(str(target), substitution.options),
                        intent="general_substitution",
                        route="substitution_catalog",
                        substitutions=substitution.options,
                        warnings=warnings,
                        debug=self._build_debug(
                            options=options,
                            constraints=constraints,
                            decision=decision,
                            parser_debug=parser_debug,
                        ),
                    )
                return self._response_for_missing_recipe(
                    conversation_id=conversation_id,
                    decision=decision,
                    warnings=warnings,
                    candidates=resolved.candidates,
                    answer_if_missing="Я пока не понимаю, для какого рецепта нужна замена. Назовите рецепт или сначала попросите найти рецепты.",
                    options=options,
                    constraints=constraints,
                    parser_debug=parser_debug,
                )
            detail = self._recipe_repository.row_to_recipe_detail(resolved.row)
            self._conversation_state_service.update_snapshot(
                conversation_id,
                selected_recipe_id=detail.recipe_id,
            )
            target = decision.entities.get("target_ingredient") or "ингредиент"
            substitution = self._substitution_service.suggest(detail, str(target))
            warnings = [*warnings, *substitution.warnings]
            if not substitution.found_in_recipe:
                fallback_answer = (
                    f'В рецепте "{detail.title}" я не нашел ингредиент "{target}". '
                    "Проверьте формулировку или выберите другой рецепт."
                )
            elif substitution.options:
                fallback_answer = self._render_substitutions_answer(
                    detail.title, str(target), substitution.options
                )
            else:
                fallback_answer = (
                    f'Для ингредиента "{target}" в рецепте "{detail.title}" пока нет готовых замен.'
                )
            llm_result = self._answer_generator.generate_substitution_answer(
                user_message=message,
                fallback_answer=fallback_answer,
                detail=detail,
                substitutions=substitution.options,
                warnings=warnings,
                constraints=constraints,
                recent_dialog=recent_dialog,
            )
            self._chat_debug_llm(options, llm_result)
            return ChatResponse(
                conversation_id=conversation_id,
                answer=llm_result.answer,
                intent=decision.intent,
                route=decision.route,
                selected_recipe=detail,
                substitutions=substitution.options,
                warnings=warnings,
                sources=[self._source_from_detail(detail)],
                debug=self._build_debug(
                    options=options,
                    constraints=constraints,
                    decision=decision,
                    llm_result=llm_result,
                    parser_debug=parser_debug,
                ),
            )

        if decision.intent == "similar_recipes":
            resolved = self._resolve_recipe(conversation_id, decision)
            if resolved.row is None:
                return self._response_for_missing_recipe(
                    conversation_id=conversation_id,
                    decision=decision,
                    warnings=warnings,
                    candidates=resolved.candidates,
                    answer_if_missing="Сначала выберите рецепт: покажите список или уточните название блюда.",
                    options=options,
                    constraints=constraints,
                    parser_debug=parser_debug,
                )
            base_row = resolved.row
            similar_rows = self._vector_search_service.similar_by_recipe_id(
                int(base_row["id"]),
                top_k=options.top_k,
            )
            similar_rows = [
                row for row in similar_rows
                if int(row.get("id") or 0) != int(base_row["id"])
            ]
            self._chat_debug_log(
                options,
                "similar base_recipe_id=%s vector_neighbors=%d",
                int(base_row["id"]),
                len(similar_rows),
            )
            execution = self._search_service.similar_recipes(
                normalized_query=message,
                base_rows=similar_rows,
                constraints=constraints,
                top_k=options.top_k,
                exclude_recipe_ids=exclude_recipe_ids,
            )
            self._chat_debug_search(options, "similar_recipes rerank", execution)
            recipes = self._rows_to_cards(execution.final_results)
            self._conversation_state_service.update_snapshot(
                conversation_id,
                last_recipe_results=[card.recipe_id for card in recipes],
            )
            fallback_answer = self._render_similar_answer(
                base_row.get("title") or "выбранного рецепта", recipes
            )
            llm_result = self._answer_generator.generate_recipe_list_answer(
                intent=decision.intent,
                user_message=message,
                fallback_answer=fallback_answer,
                recipes=recipes,
                warnings=warnings,
                constraints=constraints,
                sources=self._sources_from_cards(recipes),
                recent_dialog=recent_dialog,
            )
            self._chat_debug_llm(options, llm_result)
            return ChatResponse(
                conversation_id=conversation_id,
                answer=llm_result.answer,
                intent=decision.intent,
                route=decision.route,
                recipes=recipes,
                warnings=warnings,
                sources=self._sources_from_cards(recipes),
                debug=self._build_debug(
                    options=options,
                    constraints=constraints,
                    decision=decision,
                    execution=execution,
                    llm_result=llm_result,
                    parser_debug=parser_debug,
                ),
            )

        if decision.intent == "conversation_recall":
            recent_messages = self._conversation_state_service.get_recent_messages(conversation_id, limit=6)
            self._chat_debug_log(
                options,
                "conversation_recall messages_considered=%d",
                len(recent_messages),
            )
            answer = self._render_conversation_recall_answer(recent_messages)
            return ChatResponse(
                conversation_id=conversation_id,
                answer=answer,
                intent=decision.intent,
                route=decision.route,
                warnings=warnings,
                sources=[],
                debug=self._build_debug(
                    options=options,
                    constraints=constraints,
                    decision=decision,
                    parser_debug=parser_debug,
                ),
            )

        default_fallback = "Я могу помочь найти рецепт, показать детали, БЖУ или варианты замены ингредиента."
        llm_result = None
        if options.include_debug:
            self._chat_debug_log(
                options,
                "fallback intent=%s route=%s (static answer; optional LLM for debug block)",
                decision.intent,
                decision.route,
            )
            llm_result = self._answer_generator.generate_missing_context_answer(
                user_message=message,
                fallback_answer=default_fallback,
                warnings=warnings,
            )
            self._chat_debug_llm(options, llm_result)
        return ChatResponse(
            conversation_id=conversation_id,
            answer=default_fallback,
            intent=decision.intent,
            route=decision.route,
            warnings=warnings,
            sources=[],
            debug=self._build_debug(
                options=options,
                constraints=constraints,
                decision=decision,
                llm_result=llm_result,
                parser_debug=parser_debug,
            ),
        )

    def _renumber_event_menu(
        self, menu: list[EventMenuGroup]
    ) -> tuple[list[EventMenuGroup], list[RecipeCard]]:
        flat: list[RecipeCard] = []
        n = 1
        new_groups: list[EventMenuGroup] = []
        for group in menu:
            cards = [c.model_copy(update={"rank": n + i}) for i, c in enumerate(group.recipes)]
            n += len(cards)
            flat.extend(cards)
            new_groups.append(group.model_copy(update={"recipes": cards}))
        return new_groups, flat

    def _render_event_menu_fallback(
        self,
        *,
        event_profile: EventProfile,
        event_menu: list[EventMenuGroup],
        reasons_by_id: dict[int, list[str]],
        partial: bool,
        empty: bool,
    ) -> str:
        if empty:
            return (
                "Я не нашел подходящих рецептов под это событие с текущими ограничениями. "
                "Можно ослабить условия: убрать часть исключений, увеличить время приготовления "
                "или выбрать другой формат меню."
            )
        lines: list[str] = []
        label = event_profile.event_type or "событие"
        guests = event_profile.guests_count
        if guests:
            lines.append(f"Я подобрал варианты меню на {guests} человек ({label}).")
        else:
            lines.append(f"Я подобрал варианты меню под ваш запрос ({label}).")
        if partial:
            lines.append(
                "Я нашел несколько рецептов, которые могут подойти под событие, "
                "но не смог собрать полное меню по всем разделам."
            )
        for group in event_menu:
            lines.append(f"\n{group.title}:")
            for card in group.recipes:
                why_list = reasons_by_id.get(card.recipe_id, [])
                why = why_list[0] if why_list else "может подойти; проверьте состав и порции в карточке рецепта"
                lines.append(f"{card.rank}. {card.title}\n   Почему подходит: {why}")
        lines.append(
            "\nПроверьте состав конкретных продуктов и возможные следы аллергенов на упаковке."
        )
        return "\n".join(lines).strip()

    def _dispatch_event_recommendation(
        self,
        *,
        conversation_id: str,
        message: str,
        options: ChatOptions,
        constraints: QueryConstraints,
        decision: IntentDecision,
        warnings: list[str],
        parser_debug: dict | None = None,
        exclude_recipe_ids: frozenset[int] | None = None,
        recent_dialog: list[dict[str, str]] | None = None,
    ) -> ChatResponse:
        raw_ep = decision.entities.get("event_profile")
        event_profile: EventProfile | None = None
        if isinstance(raw_ep, dict) and raw_ep:
            try:
                event_profile = EventProfile.model_validate(raw_ep)
            except Exception:
                event_profile = None
        if event_profile is None or not event_profile.event_type:
            extracted = extract_event_profile(message, max_guests=self._settings.event_max_guests)
            if extracted:
                event_profile = extracted
        if event_profile is None:
            event_profile = EventProfile(
                event_type="generic_event",
                meal_roles=["main", "dessert"],
                vibe=[],
            )

        if event_profile.event_type == "generic_event" and not event_profile.meal_roles:
            event_profile = event_profile.model_copy(update={"meal_roles": ["main", "dessert"]})

        search_message = build_event_search_query(message, event_profile)
        mult = max(1, self._settings.event_candidate_multiplier)
        candidate_k = max(options.top_k * mult, self._settings.event_min_candidates)

        execution = self._search_service.search(
            search_message,
            constraints=constraints,
            top_k=candidate_k,
            exclude_recipe_ids=exclude_recipe_ids,
        )
        self._chat_debug_search(options, "event recommendation search", execution)
        pool = [dict(r) for r in execution.final_results]
        ranked = self._event_ranker.rank(
            rows=pool,
            event_profile=event_profile,
            constraints=constraints,
            top_k=options.top_k,
        )
        event_menu = self._menu_composer.compose(
            ranked_rows=ranked,
            event_profile=event_profile,
            top_k=options.top_k,
            row_to_card=self._recipe_repository.row_to_recipe_card,
        )
        event_menu, flat_cards = self._renumber_event_menu(event_menu)
        self._conversation_state_service.update_snapshot(
            conversation_id,
            last_recipe_results=[card.recipe_id for card in flat_cards],
            selected_recipe_id=None,
            last_event_profile=event_profile.model_dump(mode="json", exclude_none=True),
        )
        reasons_by_id = {int(r.get("id") or 0): r.get("event_reasons") or [] for r in ranked}
        roles_needed = len(event_profile.meal_roles or [])
        filled_roles = len(event_menu)
        partial = bool(flat_cards and roles_needed > 0 and filled_roles < roles_needed)
        fallback_answer = self._render_event_menu_fallback(
            event_profile=event_profile,
            event_menu=event_menu,
            reasons_by_id=reasons_by_id,
            partial=partial,
            empty=not flat_cards,
        )
        llm_result = self._answer_generator.generate_event_menu_answer(
            user_message=message,
            fallback_answer=fallback_answer,
            event_profile=event_profile,
            event_menu=event_menu,
            warnings=warnings,
            recipes=flat_cards,
            constraints=constraints,
            sources=self._sources_from_cards(flat_cards),
            recent_dialog=recent_dialog,
        )
        self._chat_debug_llm(options, llm_result)

        event_debug = {
            "event_profile": event_profile.model_dump(mode="json", exclude_none=True),
            "event_ranker": {
                "candidate_count": len(pool),
                "ranked_count": len(ranked),
            },
            "ranked_preview": [
                {
                    "recipe_id": int(r.get("id") or 0),
                    "title": r.get("title"),
                    "event_score": r.get("event_score"),
                    "event_roles": r.get("event_roles"),
                    "event_reasons": r.get("event_reasons"),
                    "matched_by": r.get("matched_by"),
                }
                for r in ranked[: min(20, len(ranked))]
            ],
        }

        return ChatResponse(
            conversation_id=conversation_id,
            answer=llm_result.answer,
            intent=decision.intent,
            route=decision.route,
            recipes=flat_cards,
            event_profile=event_profile,
            event_menu=event_menu,
            warnings=warnings,
            sources=self._sources_from_cards(flat_cards),
            debug=self._build_debug(
                options=options,
                constraints=constraints,
                decision=decision,
                execution=execution,
                llm_result=llm_result,
                parser_debug=parser_debug,
                event_recommendation=event_debug,
            ),
        )

    def _resolve_recipe(self, conversation_id: str, decision: IntentDecision) -> ResolvedRecipe:
        reference = decision.entities.get("recipe_reference")
        recipe_id = self._conversation_state_service.resolve_reference(conversation_id, reference)
        if recipe_id is not None:
            row = self._recipe_repository.get_recipe_row_by_id(recipe_id)
            return ResolvedRecipe(row=row, candidates=[])

        title_query = decision.entities.get("recipe_title_query")
        if title_query:
            contextual_candidates = self._find_title_in_recent_results(
                conversation_id=conversation_id,
                title_query=str(title_query),
            )
            if len(contextual_candidates) == 1:
                return ResolvedRecipe(row=contextual_candidates[0], candidates=[])
            if contextual_candidates:
                return ResolvedRecipe(row=None, candidates=contextual_candidates)

            candidates = self._recipe_repository.search_recipe_rows_by_text(str(title_query), limit=3)
            if len(candidates) == 1:
                return ResolvedRecipe(row=candidates[0], candidates=[])
            return ResolvedRecipe(row=None, candidates=candidates)

        return ResolvedRecipe(row=None, candidates=[])

    def _find_title_in_recent_results(self, *, conversation_id: str, title_query: str) -> list[dict]:
        snapshot = self._conversation_state_service.get_snapshot(conversation_id)
        if not snapshot.last_recipe_results:
            return []

        rows = self._recipe_repository.get_recipe_rows_by_ids(snapshot.last_recipe_results)
        query_tokens = self._normalized_tokens(title_query)
        if not query_tokens:
            return []

        matched_rows: list[dict] = []
        for row in rows:
            title = str(row.get("title") or "")
            title_tokens = self._normalized_tokens(title)
            if query_tokens.issubset(title_tokens):
                matched_rows.append(row)
        return matched_rows[:3]

    def _normalized_tokens(self, value: str) -> set[str]:
        return {
            token
            for token in re.split(r"[^а-яёa-z0-9]+", value.lower())
            if len(token) >= 3
        }

    def _should_search_candidates_for_nutrition(
        self,
        decision: IntentDecision,
        constraints: QueryConstraints,
    ) -> bool:
        return bool(
            constraints.include_ingredients
            or constraints.exclude_ingredients
            or constraints.allergy_exclusions
            or constraints.meal_type
            or decision.entities.get("recipe_title_query")
        )

    def _response_for_missing_recipe(
        self,
        *,
        conversation_id: str,
        decision: IntentDecision,
        warnings: list[str],
        candidates: list[dict],
        answer_if_missing: str,
        options: ChatOptions | None = None,
        constraints: QueryConstraints | None = None,
        parser_debug: dict | None = None,
    ) -> ChatResponse:
        cards = self._rows_to_cards(candidates)
        if cards:
            self._conversation_state_service.update_snapshot(
                conversation_id,
                last_recipe_results=[card.recipe_id for card in cards],
            )
            answer = "Я нашел несколько похожих рецептов. Уточните, какой именно нужен:\n" + "\n".join(
                f"{card.rank}. {card.title}" for card in cards
            )
        else:
            answer = answer_if_missing
        debug = None
        if options is not None and constraints is not None:
            debug = self._build_debug(
                options=options,
                constraints=constraints,
                decision=decision,
                parser_debug=parser_debug,
            )
        return ChatResponse(
            conversation_id=conversation_id,
            answer=answer,
            intent=decision.intent,
            route=decision.route,
            recipes=cards,
            warnings=warnings,
            sources=self._sources_from_cards(cards),
            debug=debug,
        )

    def _rows_to_cards(self, rows: list[dict]) -> list[RecipeCard]:
        return [
            self._recipe_repository.row_to_recipe_card(row, rank=idx)
            for idx, row in enumerate(rows, start=1)
        ]

    def _sources_from_cards(self, cards: list[RecipeCard]) -> list[SourceInfo]:
        return [
            SourceInfo(type="recipe", recipe_id=card.recipe_id, title=card.title, url=card.recipe_url)
            for card in cards
        ]

    def _source_from_detail(self, detail: RecipeDetail) -> SourceInfo:
        return SourceInfo(
            type="recipe",
            recipe_id=detail.recipe_id,
            title=detail.title,
            url=detail.recipe_url,
        )

    def _warnings_from_constraints(self, constraints: QueryConstraints) -> list[str]:
        warnings: list[str] = []
        if constraints.allergy_exclusions or constraints.restriction_type in {
            "forbidden",
            "allergy_or_forbidden",
        }:
            warnings.append(ALLERGY_WARNING)
        return warnings

    def _render_recipe_list_answer(self, intent: str, recipes: list[RecipeCard]) -> str:
        if not recipes:
            return (
                "Я не нашел подходящих рецептов в базе. Могу предложить изменить условия поиска: "
                "убрать часть ограничений, выбрать другой ингредиент или искать похожие блюда."
            )

        intro = "Я нашел подходящие рецепты:"
        if intent == "recommend_recipes":
            intro = "Я нашел несколько подходящих вариантов:"
        if intent == "allergy_or_exclusion":
            intro = "Я подобрал варианты с учетом ваших ограничений:"
        body = "\n".join(f"{card.rank}. {card.title}" for card in recipes)
        return f"{intro}\n{body}"

    def _render_nutrition_candidate_answer(
        self,
        recipes: list[RecipeCard],
        *,
        nutrients: list[str | None],
    ) -> str:
        if not recipes:
            return (
                "Я не нашел подходящих рецептов, по которым можно показать КБЖУ. "
                "Попробуйте уточнить название блюда или изменить условия поиска."
            )
        selected = {item for item in nutrients if item}
        if not selected or "bju" in selected:
            selected = {"calories", "protein", "fat", "carbs"}

        body = "\n".join(
            f"{card.rank}. {card.title}: {self._render_card_nutrition(card, selected)}"
            for card in recipes
        )
        return f"Вот значения на 100 г для рецептов под ваш запрос:\n{body}"

    def _render_card_nutrition(self, card: RecipeCard, nutrients: set[str]) -> str:
        parts: list[str] = []
        if "calories" in nutrients:
            parts.append(f"{card.calories_kcal} кКал")
        if "protein" in nutrients:
            parts.append(f"{card.protein_g} г белка")
        if "fat" in nutrients:
            parts.append(f"{card.fat_g} г жиров")
        if "carbs" in nutrients:
            parts.append(f"{card.carbs_g} г углеводов")
        return ", ".join(parts)

    def _render_recipe_detail_answer(self, message: str, detail: RecipeDetail) -> str:
        lowered = message.lower()
        if "ингредиент" in lowered:
            ingredients = ", ".join(item.name for item in detail.ingredients[:10])
            return f'Для рецепта "{detail.title}" нужны: {ingredients}.'
        if "шаг" in lowered or "готовить" in lowered:
            steps = "; ".join(step.text for step in detail.steps[:3])
            return f'Для рецепта "{detail.title}" первые шаги такие: {steps}'
        return (
            f'Показываю рецепт "{detail.title}". В нем {len(detail.ingredients)} ингредиентов '
            f"и {len(detail.steps)} шагов приготовления."
        )

    def _render_substitutions_answer(
        self,
        title: str,
        target: str,
        options: list[SubstitutionOption],
    ) -> str:
        rendered = "\n".join(
            f"- {item.name}: {item.note or 'подходит как замена'}"
            for item in options
        )
        return f'В рецепте "{title}" вместо "{target}" можно попробовать:\n{rendered}'

    def _render_general_substitutions_answer(
        self,
        target: str,
        options: list[SubstitutionOption],
    ) -> str:
        if not options:
            return f'Для ингредиента "{target}" пока нет готовых замен в rule-based каталоге.'
        rendered = "\n".join(
            f"- {item.name}: {item.note or 'подходит как замена'}"
            for item in options
        )
        return f'Вместо "{target}" обычно можно попробовать:\n{rendered}'

    def _render_similar_answer(self, base_title: str, recipes: list[RecipeCard]) -> str:
        if not recipes:
            return "Я не нашел похожих рецептов с учетом текущих ограничений."
        body = "\n".join(f"{card.rank}. {card.title}" for card in recipes)
        return f'Вот похожие варианты для "{base_title}":\n{body}'

    def _render_conversation_recall_answer(self, messages: list[tuple[str, str]]) -> str:
        user_messages = [content.strip() for role, content in messages if role == "user" and content.strip()]
        if not user_messages:
            return "Пока в этом диалоге нет предыдущих пользовательских запросов."

        recent = user_messages[-3:]
        if len(recent) == 1:
            return f"Ранее в этом диалоге вы спрашивали: {recent[0]}"

        rendered = "\n".join(f"- {item}" for item in recent)
        return f"Вот что вы спрашивали ранее в этом диалоге:\n{rendered}"

    def _build_debug(
        self,
        *,
        options: ChatOptions,
        constraints: QueryConstraints,
        decision: IntentDecision,
        execution=None,
        llm_result: AnswerGenerationResult | None = None,
        parser_debug: dict | None = None,
        event_recommendation: dict | None = None,
    ) -> ChatDebugInfo | None:
        if not options.include_debug:
            return None
        return ChatDebugInfo(
            normalized_query=getattr(execution, "normalized_query", None),
            constraints=constraints,
            intent_decision=decision,
            vector_results=self._simplify_rows(getattr(execution, "vector_results", [])),
            keyword_results=self._simplify_rows(getattr(execution, "keyword_results", [])),
            final_results=self._simplify_rows(getattr(execution, "final_results", [])),
            event_recommendation=event_recommendation,
            llm=self._build_llm_debug(llm_result),
            parser=parser_debug,
        )

    def _build_llm_debug(self, llm_result: AnswerGenerationResult | None) -> dict | None:
        if llm_result is None:
            return None
        return {
            "used_llm": llm_result.used_llm,
            "fallback_reason": llm_result.fallback_reason,
            "latency_ms": llm_result.latency_ms,
            "postcheck_passed": llm_result.postcheck_passed,
            "postcheck_errors": llm_result.postcheck_errors,
        }

    def _simplify_rows(self, rows: list[dict]) -> list[dict]:
        out: list[dict] = []
        for row in rows:
            out.append(
                {
                    "recipe_id": int(row["id"]),
                    "title": row.get("title"),
                    "recipe_url": row.get("recipe_url"),
                    "similarity": row.get("similarity"),
                    "score": row.get("final_score") or row.get("keyword_score"),
                    "matched_by": row.get("matched_by", []),
                }
            )
        return out
