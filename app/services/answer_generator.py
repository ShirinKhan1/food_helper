from __future__ import annotations

import logging
import time

import httpx

from app.schemas.event import EventMenuGroup, EventProfile
from app.schemas.search import QueryConstraints
from app.services.llm.base import LLMClient, LLMGenerateRequest
from app.services.llm.context import LLMAnswerContext
from app.services.llm.null import NullLLMClient
from app.services.llm.postcheck import PostcheckPolicy, validate_llm_answer
from app.services.llm.prompts import SYSTEM_PROMPT, build_user_prompt, truncate_llm_context
from app.services.llm.result import AnswerGenerationResult

LOGGER = logging.getLogger(__name__)

AUTO_ALLOWLIST = {
    "search_recipes",
    "recommend_recipes",
    "event_recommendation",
    "allergy_or_exclusion",
    "similar_recipes",
    "recipe_details",
    "nutrition_question",
    "ingredient_substitution",
    "general_substitution",
}


class AnswerGenerator:
    def __init__(
        self,
        *,
        llm_client: LLMClient,
        temperature: float,
        max_tokens: int,
        num_ctx: int,
        think: bool,
        llm_enabled: bool,
        answer_mode: str,
        llm_postcheck_enabled: bool,
        llm_strict_context: bool,
        llm_max_answer_chars: int,
        llm_strip_think_tags: bool,
        llm_log_prompts: bool,
        llm_log_responses: bool,
        llm_min_recipes_for_list_answer: int,
        llm_max_context_recipes: int,
        llm_max_context_ingredients: int,
        llm_max_context_steps: int,
    ) -> None:
        self._llm_client = llm_client
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._num_ctx = num_ctx
        self._think = think
        self._llm_enabled = llm_enabled
        self._answer_mode = answer_mode
        self._llm_postcheck_enabled = llm_postcheck_enabled
        self._llm_strict_context = llm_strict_context
        self._llm_max_answer_chars = llm_max_answer_chars
        self._llm_strip_think_tags = llm_strip_think_tags
        self._llm_log_prompts = llm_log_prompts
        self._llm_log_responses = llm_log_responses
        self._llm_min_recipes_for_list_answer = llm_min_recipes_for_list_answer
        self._llm_max_context_recipes = llm_max_context_recipes
        self._llm_max_context_ingredients = llm_max_context_ingredients
        self._llm_max_context_steps = llm_max_context_steps

    def generate_recipe_list_answer(
        self,
        *,
        intent: str,
        user_message: str,
        fallback_answer: str,
        recipes: list[RecipeCard],
        warnings: list[str],
        constraints: QueryConstraints | None = None,
        sources: list[SourceInfo] | None = None,
        recent_dialog: list[dict[str, str]] | None = None,
    ) -> AnswerGenerationResult:
        scenario = "similar_recipes" if intent == "similar_recipes" else "recipe_list"
        context = LLMAnswerContext(
            scenario=scenario,
            user_message=user_message,
            constraints=constraints,
            recipes=recipes,
            warnings=warnings,
            sources=sources or [],
            recent_dialog=recent_dialog,
        )
        return self._generate_or_fallback(
            scenario=scenario,
            intent=intent,
            user_message=user_message,
            fallback_answer=fallback_answer,
            context=context,
            allow_llm=len(recipes) >= self._llm_min_recipes_for_list_answer,
        )

    def generate_recipe_detail_answer(
        self,
        *,
        user_message: str,
        fallback_answer: str,
        detail: RecipeDetail,
        warnings: list[str],
        constraints: QueryConstraints | None = None,
        sources: list[SourceInfo] | None = None,
        recent_dialog: list[dict[str, str]] | None = None,
    ) -> AnswerGenerationResult:
        context = LLMAnswerContext(
            scenario="recipe_detail",
            user_message=user_message,
            constraints=constraints,
            recipe_detail=detail,
            warnings=warnings,
            sources=sources or [],
            recent_dialog=recent_dialog,
        )
        return self._generate_or_fallback(
            scenario="recipe_detail",
            intent="recipe_details",
            user_message=user_message,
            fallback_answer=fallback_answer,
            context=context,
            allow_llm=True,
        )

    def generate_nutrition_answer(
        self,
        *,
        user_message: str,
        fallback_answer: str,
        nutrition: NutritionInfo,
        detail: RecipeDetail,
        warnings: list[str],
        constraints: QueryConstraints | None = None,
        sources: list[SourceInfo] | None = None,
        recent_dialog: list[dict[str, str]] | None = None,
    ) -> AnswerGenerationResult:
        context = LLMAnswerContext(
            scenario="nutrition",
            user_message=user_message,
            constraints=constraints,
            recipe_detail=detail,
            nutrition=nutrition,
            warnings=warnings,
            sources=sources or [],
            recent_dialog=recent_dialog,
        )
        return self._generate_or_fallback(
            scenario="nutrition",
            intent="nutrition_question",
            user_message=user_message,
            fallback_answer=fallback_answer,
            context=context,
            allow_llm=True,
        )

    def generate_nutrition_candidates_answer(
        self,
        *,
        intent: str,
        user_message: str,
        fallback_answer: str,
        recipes: list[RecipeCard],
        warnings: list[str],
        constraints: QueryConstraints | None = None,
        sources: list[SourceInfo] | None = None,
        recent_dialog: list[dict[str, str]] | None = None,
    ) -> AnswerGenerationResult:
        context = LLMAnswerContext(
            scenario="nutrition_candidates",
            user_message=user_message,
            constraints=constraints,
            recipes=recipes,
            warnings=warnings,
            sources=sources or [],
            recent_dialog=recent_dialog,
        )
        return self._generate_or_fallback(
            scenario="nutrition_candidates",
            intent=intent,
            user_message=user_message,
            fallback_answer=fallback_answer,
            context=context,
            allow_llm=len(recipes) >= self._llm_min_recipes_for_list_answer,
        )

    def generate_substitution_answer(
        self,
        *,
        user_message: str,
        fallback_answer: str,
        detail: RecipeDetail | None,
        substitutions: list[SubstitutionOption],
        warnings: list[str],
        constraints: QueryConstraints | None = None,
        recent_dialog: list[dict[str, str]] | None = None,
    ) -> AnswerGenerationResult:
        context = LLMAnswerContext(
            scenario="ingredient_substitution",
            user_message=user_message,
            constraints=constraints,
            recipe_detail=detail,
            substitutions=substitutions,
            warnings=warnings,
            recent_dialog=recent_dialog,
        )
        return self._generate_or_fallback(
            scenario="ingredient_substitution",
            intent="ingredient_substitution",
            user_message=user_message,
            fallback_answer=fallback_answer,
            context=context,
            allow_llm=bool(substitutions),
        )

    def generate_general_substitution_answer(
        self,
        *,
        user_message: str,
        fallback_answer: str,
        substitutions: list[SubstitutionOption],
        warnings: list[str],
        constraints: QueryConstraints | None = None,
        recent_dialog: list[dict[str, str]] | None = None,
    ) -> AnswerGenerationResult:
        context = LLMAnswerContext(
            scenario="general_substitution",
            user_message=user_message,
            constraints=constraints,
            substitutions=substitutions,
            warnings=warnings,
            recent_dialog=recent_dialog,
        )
        return self._generate_or_fallback(
            scenario="general_substitution",
            intent="general_substitution",
            user_message=user_message,
            fallback_answer=fallback_answer,
            context=context,
            allow_llm=bool(substitutions),
        )

    def generate_empty_results_answer(
        self,
        *,
        user_message: str,
        fallback_answer: str,
        warnings: list[str],
    ) -> AnswerGenerationResult:
        context = LLMAnswerContext(
            scenario="empty_results",
            user_message=user_message,
            warnings=warnings,
        )
        return self._generate_or_fallback(
            scenario="empty_results",
            intent="search_recipes",
            user_message=user_message,
            fallback_answer=fallback_answer,
            context=context,
            allow_llm=False,
        )

    def generate_missing_context_answer(
        self,
        *,
        user_message: str,
        fallback_answer: str,
        warnings: list[str],
    ) -> AnswerGenerationResult:
        context = LLMAnswerContext(
            scenario="missing_context",
            user_message=user_message,
            warnings=warnings,
        )
        return self._generate_or_fallback(
            scenario="missing_context",
            intent="fallback",
            user_message=user_message,
            fallback_answer=fallback_answer,
            context=context,
            allow_llm=False,
        )

    def generate_event_menu_answer(
        self,
        *,
        user_message: str,
        fallback_answer: str,
        event_profile: EventProfile,
        event_menu: list[EventMenuGroup],
        warnings: list[str],
        recipes: list[RecipeCard],
        constraints: QueryConstraints | None = None,
        sources: list[SourceInfo] | None = None,
        recent_dialog: list[dict[str, str]] | None = None,
    ) -> AnswerGenerationResult:
        context = LLMAnswerContext(
            scenario="event_menu",
            user_message=user_message,
            constraints=constraints,
            recipes=recipes,
            warnings=warnings,
            sources=sources or [],
            event_profile=event_profile.model_dump(mode="json", exclude_none=True),
            event_menu=[g.model_dump(mode="json") for g in event_menu],
            recent_dialog=recent_dialog,
        )
        return self._generate_or_fallback(
            scenario="event_menu",
            intent="event_recommendation",
            user_message=user_message,
            fallback_answer=fallback_answer,
            context=context,
            allow_llm=bool(recipes),
        )

    def _generate_or_fallback(
        self,
        *,
        scenario: str,
        intent: str,
        user_message: str,
        fallback_answer: str,
        context: LLMAnswerContext,
        allow_llm: bool,
    ) -> AnswerGenerationResult:
        reason = self._fallback_reason(intent=intent, allow_llm=allow_llm)
        if reason:
            return AnswerGenerationResult(answer=fallback_answer, used_llm=False, fallback_reason=reason)

        prompt_context = truncate_llm_context(
            context,
            max_recipes=self._llm_max_context_recipes,
            max_ingredients=self._llm_max_context_ingredients,
            max_steps=self._llm_max_context_steps,
        )
        prompt = build_user_prompt(prompt_context)
        if self._llm_log_prompts:
            LOGGER.debug("LLM prompt chars=%s preview=%r", len(prompt), prompt[:500])
        started_at = time.perf_counter()
        try:
            raw_answer = self._llm_client.generate(
                LLMGenerateRequest(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=prompt,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    num_ctx=self._num_ctx,
                    think=self._think,
                )
            )
        except (TimeoutError, httpx.TimeoutException):
            return AnswerGenerationResult(answer=fallback_answer, used_llm=False, fallback_reason="llm_timeout")
        except Exception as exc:
            LOGGER.warning("LLM call failed: %s", exc)
            return AnswerGenerationResult(answer=fallback_answer, used_llm=False, fallback_reason="llm_exception")

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        if not raw_answer.strip():
            return AnswerGenerationResult(answer=fallback_answer, used_llm=False, fallback_reason="llm_empty_response")

        if self._llm_log_responses:
            LOGGER.debug("LLM raw response chars=%s preview=%r", len(raw_answer), raw_answer[:500])

        if not self._llm_postcheck_enabled:
            return AnswerGenerationResult(
                answer=raw_answer.strip(),
                used_llm=True,
                latency_ms=latency_ms,
                prompt_chars=len(prompt),
                response_chars=len(raw_answer),
            )

        policy = PostcheckPolicy(
            scenario=scenario,
            strict_context=self._llm_strict_context,
            max_answer_chars=self._llm_max_answer_chars,
            strip_think_tags=self._llm_strip_think_tags,
        )
        postcheck = validate_llm_answer(answer=raw_answer, context=context, policy=policy)
        if not postcheck.ok:
            reason = self._reason_from_postcheck(postcheck.errors)
            return AnswerGenerationResult(
                answer=fallback_answer,
                used_llm=False,
                fallback_reason=reason,
                latency_ms=latency_ms,
                prompt_chars=len(prompt),
                response_chars=len(raw_answer),
                postcheck_passed=False,
                postcheck_errors=postcheck.errors,
            )
        return AnswerGenerationResult(
            answer=postcheck.sanitized_answer or raw_answer.strip(),
            used_llm=True,
            latency_ms=latency_ms,
            prompt_chars=len(prompt),
            response_chars=len(raw_answer),
            postcheck_passed=True,
        )

    def _fallback_reason(self, *, intent: str, allow_llm: bool) -> str | None:
        if self._answer_mode == "template":
            return "answer_mode_template"
        if not self._llm_enabled:
            return "llm_disabled"
        if isinstance(self._llm_client, NullLLMClient):
            return "llm_client_null"
        if self._answer_mode == "auto" and intent not in AUTO_ALLOWLIST:
            return "no_context"
        if not allow_llm:
            return "no_context"
        return None

    def _reason_from_postcheck(self, errors: list[str]) -> str:
        if "too_long" in errors:
            return "postcheck_too_long"
        if "hallucinated_recipe" in errors:
            return "postcheck_hallucinated_recipe"
        if "hallucinated_nutrition" in errors:
            return "postcheck_hallucinated_nutrition"
        if "medical_guarantee" in errors:
            return "postcheck_medical_guarantee"
        if "forbidden_ingredient_mentioned" in errors:
            return "postcheck_forbidden_ingredient"
        return "postcheck_failed"
