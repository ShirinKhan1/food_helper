from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.schemas.parser import ParsedUserRequest

if TYPE_CHECKING:
    from app.schemas.search import QueryConstraints
    from app.services.conversation_state import ConversationSnapshot

ALLOWED_INTENTS: set[str] = {
    "search_recipes",
    "recommend_recipes",
    "nutrition_question",
    "ingredient_substitution",
    "general_substitution",
    "recipe_details",
    "similar_recipes",
    "allergy_or_exclusion",
    "conversation_recall",
    "fallback",
}

ALLOWED_NUTRIENTS = {"calories", "protein", "fat", "carbs", "bju"}

_SQLISH = re.compile(r"\b(select|insert|update|delete|drop|from|where)\b", re.IGNORECASE)
_URLISH = re.compile(r"https?://|www\.", re.IGNORECASE)


class ParserPostcheckResult(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    sanitized: ParsedUserRequest | None = None


class ParserPostcheck:
    def __init__(self, *, max_question_chars: int = 250, target_ingredient_max_len: int = 80) -> None:
        self._max_question_chars = max_question_chars
        self._target_ingredient_max_len = target_ingredient_max_len

    def validate(
        self,
        parsed: ParsedUserRequest,
        *,
        rule_constraints: "QueryConstraints",
        snapshot: "ConversationSnapshot",
    ) -> ParserPostcheckResult:
        errors: list[str] = []

        if parsed.intent not in ALLOWED_INTENTS:
            errors.append(f"intent_not_allowed:{parsed.intent}")

        if parsed.requires_clarification:
            if parsed.clarification is None or not (parsed.clarification.question or "").strip():
                errors.append("clarification_missing_question")
        else:
            if parsed.clarification is not None:
                errors.append("clarification_must_be_null")

        if parsed.clarification and parsed.clarification.question:
            if len(parsed.clarification.question) > self._max_question_chars:
                errors.append("clarification_question_too_long")

        for n in parsed.nutrients:
            if n not in ALLOWED_NUTRIENTS:
                errors.append(f"nutrient_not_allowed:{n}")

        inc = {x.lower() for x in parsed.constraints.include_ingredients}
        exc = {x.lower() for x in parsed.constraints.exclude_ingredients}
        overlap = inc & exc
        if overlap and not parsed.requires_clarification:
            errors.append("include_exclude_overlap_without_clarification")

        rule_allergy = {x.lower() for x in rule_constraints.allergy_exclusions}
        parsed_allergy = {x.lower() for x in parsed.constraints.allergy_exclusions}
        if not rule_allergy.issubset(parsed_allergy):
            errors.append("allergy_removed_from_rules")

        rule_exc = {x.lower() for x in rule_constraints.exclude_ingredients}
        if not rule_exc.issubset(exc):
            errors.append("exclude_removed_from_rules")

        rt = rule_constraints.restriction_type
        if rt in {"allergy_or_forbidden", "forbidden"}:
            prt = parsed.constraints.restriction_type
            if prt is None or prt not in {"allergy_or_forbidden", "forbidden", rt}:
                errors.append("restriction_type_removed_from_rules")

        rr = parsed.recipe_reference
        if rr and rr.type == "rank":
            val = rr.value
            if not isinstance(val, int) or val < 1:
                errors.append("recipe_reference_rank_invalid")
            elif snapshot.last_recipe_results and val > len(snapshot.last_recipe_results):
                if not parsed.requires_clarification:
                    errors.append("recipe_reference_rank_out_of_range")

        if parsed.target_ingredient:
            ti = parsed.target_ingredient.strip()
            if len(ti) > self._target_ingredient_max_len:
                errors.append("target_ingredient_too_long")
            if "\n" in ti or "{" in ti or "}" in ti or "system" in ti.lower():
                errors.append("target_ingredient_suspicious")

        blob = parsed.model_dump_json()
        if _SQLISH.search(blob):
            errors.append("suspicious_sql_tokens")
        if _URLISH.search(blob):
            errors.append("suspicious_url")

        if errors:
            return ParserPostcheckResult(ok=False, errors=errors, sanitized=None)
        return ParserPostcheckResult(ok=True, errors=[], sanitized=parsed)
