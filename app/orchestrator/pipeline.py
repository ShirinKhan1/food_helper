from __future__ import annotations

from dataclasses import dataclass
import re

from app.core.config import Settings
from app.orchestrator.intent_router import IntentRouter
from app.orchestrator.query_constraints import extract_query_constraints
from app.schemas.chat import ChatDebugInfo, ChatOptions, ChatRequest, ChatResponse, IntentDecision
from app.schemas.recipe import NutritionInfo, RecipeCard, RecipeDetail, SourceInfo, SubstitutionOption
from app.schemas.search import QueryConstraints
from app.services.answer_generator import AnswerGenerator
from app.services.conversation_state import ConversationStateService
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

    def handle_chat(self, request: ChatRequest) -> ChatResponse:
        conversation_id = self._conversation_state_service.ensure_conversation(
            request.conversation_id
        )
        self._conversation_state_service.append_message(
            conversation_id,
            role="user",
            content=request.message,
        )

        constraints = extract_query_constraints(request.message)
        decision = self._router.decide(request.message)
        warnings = self._warnings_from_constraints(constraints)
        response = self._dispatch(
            conversation_id=conversation_id,
            message=request.message,
            options=request.options,
            constraints=constraints,
            decision=decision,
            warnings=warnings,
        )
        self._conversation_state_service.append_message(
            conversation_id,
            role="assistant",
            content=response.answer,
        )
        return response

    def _dispatch(
        self,
        *,
        conversation_id: str,
        message: str,
        options: ChatOptions,
        constraints: QueryConstraints,
        decision: IntentDecision,
        warnings: list[str],
    ) -> ChatResponse:
        if decision.intent in {"search_recipes", "recommend_recipes", "allergy_or_exclusion"}:
            execution = self._search_service.search(
                message,
                constraints=constraints,
                top_k=options.top_k,
            )
            recipes = self._rows_to_cards(execution.final_results)
            self._conversation_state_service.update_snapshot(
                conversation_id,
                last_recipe_results=[card.recipe_id for card in recipes],
                selected_recipe_id=None,
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
            )
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
                    )
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
                    )
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
                        ),
                    )
                return self._response_for_missing_recipe(
                    conversation_id=conversation_id,
                    decision=decision,
                    warnings=warnings,
                    candidates=resolved.candidates,
                    answer_if_missing="Я не смог однозначно определить рецепт. Напишите его название или сначала попросите найти рецепты.",
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
            )
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
            )
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
            )
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
                        debug=self._build_debug(options=options, constraints=constraints, decision=decision),
                    )
                return self._response_for_missing_recipe(
                    conversation_id=conversation_id,
                    decision=decision,
                    warnings=warnings,
                    candidates=resolved.candidates,
                    answer_if_missing="Я пока не понимаю, для какого рецепта нужна замена. Назовите рецепт или сначала попросите найти рецепты.",
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
            )
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
            execution = self._search_service.similar_recipes(
                normalized_query=message,
                base_rows=similar_rows,
                constraints=constraints,
                top_k=options.top_k,
            )
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
            )
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
                ),
            )

        if decision.intent == "conversation_recall":
            recent_messages = self._conversation_state_service.get_recent_messages(conversation_id, limit=6)
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
                ),
            )

        default_fallback = "Я могу помочь найти рецепт, показать детали, БЖУ или варианты замены ингредиента."
        llm_result = None
        if options.include_debug:
            llm_result = self._answer_generator.generate_missing_context_answer(
                user_message=message,
                fallback_answer=default_fallback,
                warnings=warnings,
            )
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
        return ChatResponse(
            conversation_id=conversation_id,
            answer=answer,
            intent=decision.intent,
            route=decision.route,
            recipes=cards,
            warnings=warnings,
            sources=self._sources_from_cards(cards),
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
            llm=self._build_llm_debug(llm_result),
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
