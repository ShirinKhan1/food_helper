from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING

import httpx

from app.core.config import Settings
from app.schemas.chat import IntentDecision
from app.schemas.event import EventProfile
from app.schemas.parser import ParsedQueryConstraints, ParsedUserRequest, RecipeReference
from app.schemas.search import QueryConstraints
from app.services.llm.base import LLMClient, LLMGenerateRequest
from app.services.llm.parser_postcheck import ParserPostcheck
from app.services.llm.parser_prompts import (
    PARSER_SYSTEM_PROMPT,
    build_parser_user_prompt,
    rule_parse_json_for_prompt,
)
from app.services.llm.parser_result import QueryParserResult
from app.orchestrator.event_extractor import merge_event_profiles

if TYPE_CHECKING:
    from app.services.conversation_state import ConversationSnapshot

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

_AUTO_MARKERS = re.compile(
    r"(без|до|не\s+|но\s+|и\s+чтобы|чтобы|исключая)",
    re.IGNORECASE,
)
_CONTEXT_RE = re.compile(
    r"(этот|этом|в\s+н[её]м|перв\w+|втор\w+|трет\w+|похож|аналог)",
    re.IGNORECASE,
)
_AMBIGUOUS = (
    "легк",
    "полезн",
    "диетическ",
    "нормальн",
    "что-нибудь",
    "что нибудь",
    "что-то ",
    "что то ",
)


def _strip_json_fences(text: str) -> str:
    s = text.strip()
    s = _FENCE_RE.sub("", s).strip()
    return s


def _recipe_ref_from_entities(entities: dict) -> RecipeReference | None:
    ref = entities.get("recipe_reference")
    if not ref or not isinstance(ref, dict):
        return None
    try:
        return RecipeReference.model_validate(ref)
    except Exception:
        return None


def _constraints_from_query(q: QueryConstraints) -> ParsedQueryConstraints:
    data = q.model_dump()
    mt = data.get("meal_type")
    if mt is not None and mt not in {"breakfast", "lunch", "dinner", "snack"}:
        data["meal_type"] = None
    return ParsedQueryConstraints.model_validate(data)


def merge_parsed_constraints_with_rules(
    parsed: ParsedUserRequest,
    rule_constraints: QueryConstraints,
) -> ParsedUserRequest:
    c = parsed.constraints.model_dump()
    r = rule_constraints.model_dump()

    c["exclude_ingredients"] = list(dict.fromkeys([*r["exclude_ingredients"], *c["exclude_ingredients"]]))
    c["allergy_exclusions"] = list(dict.fromkeys([*r["allergy_exclusions"], *c["allergy_exclusions"]]))
    c["include_ingredients"] = list(dict.fromkeys([*r["include_ingredients"], *c["include_ingredients"]]))

    if r.get("restriction_type") in {"allergy_or_forbidden", "forbidden"}:
        c["restriction_type"] = r["restriction_type"]

    numeric_keys = (
        "max_calories_kcal",
        "min_protein_g",
        "max_fat_g",
        "max_cooking_time_minutes",
        "max_difficulty",
    )
    for key in numeric_keys:
        rv, pv = r.get(key), c.get(key)
        if rv is not None and pv is not None and rv != pv:
            c[key] = rv
        elif rv is not None and pv is None:
            c[key] = rv

    for key in ("dish", "dietary_preference", "diet_goal", "meal_type"):
        rv, pv = r.get(key), c.get(key)
        if rv is not None and pv is None:
            c[key] = rv

    new_constraints = ParsedQueryConstraints.model_validate(c)
    return parsed.model_copy(update={"constraints": new_constraints})


def apply_rule_event_profile(
    parsed: ParsedUserRequest,
    rule_decision: IntentDecision,
) -> ParsedUserRequest:
    if rule_decision.intent != "event_recommendation":
        return parsed
    raw = rule_decision.entities.get("event_profile")
    if not isinstance(raw, dict):
        return parsed.model_copy(update={"intent": "event_recommendation"})
    base = EventProfile.model_validate(raw)
    merged = merge_event_profiles(base, parsed.event_profile)
    return parsed.model_copy(update={"intent": "event_recommendation", "event_profile": merged})


def parsed_from_rules(
    message: str,
    rule_decision: IntentDecision,
    rule_constraints: QueryConstraints,
) -> ParsedUserRequest:
    entities = rule_decision.entities or {}
    nutrients = list(entities.get("nutrients") or [])
    if not nutrients and entities.get("nutrient"):
        n = entities["nutrient"]
        if n == "bju":
            nutrients = ["bju"]
        elif n:
            nutrients = [n]

    ev: EventProfile | None = None
    if rule_decision.intent == "event_recommendation":
        raw_ep = rule_decision.entities.get("event_profile")
        if isinstance(raw_ep, dict):
            ev = EventProfile.model_validate(raw_ep)

    return ParsedUserRequest(
        intent=rule_decision.intent,  # type: ignore[arg-type]
        confidence=1.0,
        search_query=message.strip() or None,
        constraints=_constraints_from_query(rule_constraints),
        recipe_reference=_recipe_ref_from_entities(entities),
        recipe_title_query=entities.get("recipe_title_query"),
        target_ingredient=entities.get("target_ingredient"),
        nutrients=nutrients,
        event_profile=ev,
        requires_clarification=False,
        clarification=None,
    )


def should_use_llm_auto(
    message: str,
    rule_decision: IntentDecision,
    rule_constraints: QueryConstraints,
) -> bool:
    lowered = message.lower()
    if len(_AUTO_MARKERS.findall(lowered)) >= 2:
        return True
    if _CONTEXT_RE.search(lowered):
        return True
    words = lowered.split()
    if len(words) >= 9:
        return True
    if any(tok in lowered for tok in _AMBIGUOUS):
        return True
    if rule_decision.intent == "fallback":
        return True
    if rule_constraints.include_ingredients and rule_constraints.exclude_ingredients:
        inc = {x.lower() for x in rule_constraints.include_ingredients}
        exc = {x.lower() for x in rule_constraints.exclude_ingredients}
        if inc & exc:
            return True
    if (
        "замен" in lowered
        and ("найди" in lowered or "поиск" in lowered or "рецепт" in lowered)
        and (rule_constraints.exclude_ingredients or rule_constraints.include_ingredients)
    ):
        return True
    return False


class LLMQueryParser:
    def __init__(
        self,
        *,
        settings: Settings,
        llm_client: LLMClient | None,
        postcheck: ParserPostcheck,
    ) -> None:
        self._settings = settings
        self._llm = llm_client
        self._postcheck = postcheck

    def parse(
        self,
        *,
        message: str,
        rule_decision: IntentDecision,
        rule_constraints: QueryConstraints,
        recent_messages: list[tuple[str, str]],
        conversation_snapshot: "ConversationSnapshot",
    ) -> QueryParserResult:
        mode = self._settings.query_parser_mode
        if mode == "rules" or not self._settings.llm_query_parser_enabled:
            reason = "parser_mode_rules" if mode == "rules" else "parser_disabled"
            parsed = parsed_from_rules(message, rule_decision, rule_constraints)
            return QueryParserResult(parsed=parsed, used_llm=False, fallback_reason=reason)

        if self._llm is None:
            parsed = parsed_from_rules(message, rule_decision, rule_constraints)
            return QueryParserResult(parsed=parsed, used_llm=False, fallback_reason="parser_client_null")

        if mode == "auto" and not should_use_llm_auto(message, rule_decision, rule_constraints):
            parsed = parsed_from_rules(message, rule_decision, rule_constraints)
            return QueryParserResult(
                parsed=parsed,
                used_llm=False,
                fallback_reason="parser_auto_skipped_simple_query",
            )

        return self._parse_with_llm(
            message=message,
            rule_decision=rule_decision,
            rule_constraints=rule_constraints,
            recent_messages=recent_messages,
            conversation_snapshot=conversation_snapshot,
        )

    def _parse_with_llm(
        self,
        *,
        message: str,
        rule_decision: IntentDecision,
        rule_constraints: QueryConstraints,
        recent_messages: list[tuple[str, str]],
        conversation_snapshot: "ConversationSnapshot",
    ) -> QueryParserResult:
        rules_fallback = parsed_from_rules(message, rule_decision, rule_constraints)
        recent_json = json.dumps(
            [{"role": r, "content": c} for r, c in recent_messages],
            ensure_ascii=False,
        )
        state_json = json.dumps(
            {
                "last_recipe_results": conversation_snapshot.last_recipe_results,
                "selected_recipe_id": conversation_snapshot.selected_recipe_id,
                "last_event_profile": conversation_snapshot.last_event_profile,
            },
            ensure_ascii=False,
        )
        rule_json = rule_parse_json_for_prompt(
            rule_decision=rule_decision,
            rule_constraints=rule_constraints,
        )
        user_prompt = build_parser_user_prompt(
            message=message,
            recent_messages_json=recent_json,
            conversation_state_json=state_json,
            rule_parse_json=rule_json,
        )
        prompt_chars = len(PARSER_SYSTEM_PROMPT) + len(user_prompt)

        t0 = time.perf_counter()
        try:
            raw = self._llm.generate(
                LLMGenerateRequest(
                    system_prompt=PARSER_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=self._settings.llm_query_parser_temperature,
                    max_tokens=self._settings.llm_query_parser_max_tokens,
                    num_ctx=self._settings.llm_query_parser_num_ctx,
                    think=False,
                )
            )
        except (httpx.TimeoutException, TimeoutError):
            return self._fallback(
                rules_fallback,
                "parser_llm_timeout",
                prompt_chars=prompt_chars,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
        except Exception:
            return self._fallback(
                rules_fallback,
                "parser_llm_exception",
                prompt_chars=prompt_chars,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        latency_ms = int((time.perf_counter() - t0) * 1000)
        response_chars = len(raw or "")

        if not (raw or "").strip():
            return self._fallback(
                rules_fallback,
                "parser_empty_response",
                prompt_chars=prompt_chars,
                response_chars=response_chars,
                latency_ms=latency_ms,
            )

        cleaned = _strip_json_fences(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return self._fallback(
                rules_fallback,
                "parser_invalid_json",
                prompt_chars=prompt_chars,
                response_chars=response_chars,
                latency_ms=latency_ms,
            )

        try:
            parsed = ParsedUserRequest.model_validate(data)
        except Exception:
            return self._fallback(
                rules_fallback,
                "parser_schema_validation_failed",
                prompt_chars=prompt_chars,
                response_chars=response_chars,
                latency_ms=latency_ms,
            )

        parsed = merge_parsed_constraints_with_rules(parsed, rule_constraints)
        parsed = apply_rule_event_profile(parsed, rule_decision)

        postcheck_passed: bool | None = None
        postcheck_errors: list[str] = []
        if self._settings.llm_query_parser_postcheck_enabled:
            pr = self._postcheck.validate(parsed, rule_constraints=rule_constraints, snapshot=conversation_snapshot)
            postcheck_passed = pr.ok
            postcheck_errors = pr.errors
            if not pr.ok or pr.sanitized is None:
                return QueryParserResult(
                    parsed=rules_fallback,
                    used_llm=True,
                    fallback_reason="parser_postcheck_failed",
                    latency_ms=latency_ms,
                    prompt_chars=prompt_chars,
                    response_chars=response_chars,
                    postcheck_passed=False,
                    postcheck_errors=postcheck_errors,
                )
            parsed = pr.sanitized
            parsed = apply_rule_event_profile(parsed, rule_decision)

        return QueryParserResult(
            parsed=parsed,
            used_llm=True,
            fallback_reason=None,
            latency_ms=latency_ms,
            prompt_chars=prompt_chars,
            response_chars=response_chars,
            postcheck_passed=postcheck_passed,
            postcheck_errors=postcheck_errors,
        )

    def _fallback(
        self,
        parsed: ParsedUserRequest,
        reason: str,
        *,
        prompt_chars: int | None = None,
        response_chars: int | None = None,
        latency_ms: int | None = None,
    ) -> QueryParserResult:
        used = reason not in {
            "parser_mode_rules",
            "parser_disabled",
            "parser_client_null",
            "parser_auto_skipped_simple_query",
        }
        return QueryParserResult(
            parsed=parsed,
            used_llm=used,
            fallback_reason=reason,
            latency_ms=latency_ms,
            prompt_chars=prompt_chars,
            response_chars=response_chars,
            postcheck_passed=None,
            postcheck_errors=[],
        )
