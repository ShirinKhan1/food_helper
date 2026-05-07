from __future__ import annotations

from app.core.config import Settings
from app.schemas.chat import IntentDecision
from app.schemas.parser import ParsedUserRequest, ParserIntent
from app.schemas.search import QueryConstraints


def _intent_routing(intent: ParserIntent) -> tuple[str, bool, bool, bool, bool, bool]:
    """Returns route, needs_conversation_context, needs_recipe_fetch, needs_vector_search, needs_sql, needs_llm."""
    if intent == "conversation_recall":
        return "conversation_history", True, False, False, True, False
    if intent == "similar_recipes":
        return "vector_search", True, True, True, True, False
    if intent == "general_substitution":
        return "substitution_catalog", False, False, False, False, False
    if intent == "ingredient_substitution":
        return "substitution", True, True, False, True, False
    if intent == "nutrition_question":
        return "sql", True, True, False, True, False
    if intent == "recipe_details":
        return "conversation_recipe_fetch", True, True, False, True, False
    if intent in {"search_recipes", "recommend_recipes", "allergy_or_exclusion"}:
        return "hybrid_search", False, False, True, True, False
    if intent == "fallback":
        return "no_retrieval", False, False, False, False, False
    return "no_retrieval", False, False, False, False, False


def _resolve_pipeline_intent(
    parsed: ParsedUserRequest,
    rule_decision: IntentDecision,
    threshold: float,
) -> ParserIntent:
    if parsed.confidence < threshold:
        return rule_decision.intent  # type: ignore[return-value]
    if rule_decision.intent == "fallback":
        return parsed.intent
    return rule_decision.intent  # type: ignore[return-value]


def _build_entities(parsed: ParsedUserRequest, rule_decision: IntentDecision) -> dict:
    entities = dict(rule_decision.entities or {})
    if parsed.recipe_reference:
        entities["recipe_reference"] = parsed.recipe_reference.model_dump()
    if parsed.recipe_title_query is not None:
        entities["recipe_title_query"] = parsed.recipe_title_query
    if parsed.target_ingredient is not None:
        entities["target_ingredient"] = parsed.target_ingredient

    nuts = list(parsed.nutrients) if parsed.nutrients else list(entities.get("nutrients") or [])
    entities["nutrients"] = nuts
    if "bju" in nuts or len([x for x in nuts if x]) > 1:
        entities["nutrient"] = "bju"
    elif nuts:
        entities["nutrient"] = nuts[0]
    elif "nutrient" not in entities:
        entities["nutrient"] = None

    entities["include_ingredients"] = parsed.constraints.include_ingredients or entities.get(
        "include_ingredients", []
    )
    entities["exclude_ingredients"] = parsed.constraints.exclude_ingredients or entities.get(
        "exclude_ingredients", []
    )
    return entities


class ParsedRequestAdapter:
    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings

    def to_pipeline_inputs(
        self,
        *,
        parsed: ParsedUserRequest,
        rule_decision: IntentDecision,
        rule_constraints: QueryConstraints,
        message: str,
    ) -> tuple[IntentDecision, QueryConstraints, str]:
        threshold = self._settings.llm_query_parser_confidence_threshold
        chosen_intent = _resolve_pipeline_intent(parsed, rule_decision, threshold)

        pq = QueryConstraints.model_validate(parsed.constraints.model_dump())
        constraints = pq.merge(rule_constraints)

        entities = _build_entities(parsed, rule_decision)
        entities["include_ingredients"] = constraints.include_ingredients
        entities["exclude_ingredients"] = constraints.exclude_ingredients

        route, ncc, nrf, nvs, nsql, nllm = _intent_routing(chosen_intent)

        decision = IntentDecision(
            intent=chosen_intent,
            route=route,
            entities=entities,
            needs_conversation_context=ncc,
            needs_recipe_fetch=nrf,
            needs_vector_search=nvs,
            needs_sql=nsql,
            needs_llm=nllm,
        )

        msg = (parsed.search_query or message).strip() or message
        return decision, constraints, msg
