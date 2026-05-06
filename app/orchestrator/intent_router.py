from __future__ import annotations

import re

from app.orchestrator.query_constraints import extract_query_constraints
from app.schemas.chat import IntentDecision

_ORDINAL_MAP = {
    "первый": 1,
    "первом": 1,
    "первого": 1,
    "второй": 2,
    "втором": 2,
    "второго": 2,
    "третий": 3,
    "третьем": 3,
    "третьего": 3,
}
_RECIPE_REF_RE = re.compile(r"\b(первый|первом|первого|второй|втором|второго|третий|третьем|третьего)\b")
_NUTRITION_TITLE_RE = re.compile(
    r"(?:сколько|какие)\s+(?:калорий|белка|жиров|углеводов|бжу)\s+(?:в|у)\s+(.+?)[?.!]?$",
    re.IGNORECASE,
)
_DETAILS_TITLE_RE = re.compile(
    r"(?:покажи|покажи|какие ингредиенты нужны для|как готовить)\s+(.+?)[?.!]?$",
    re.IGNORECASE,
)
_SUBSTITUTION_RE = re.compile(
    r"(?:заменить|замену для|вместо)\s+([а-яёa-z0-9\-%\s]+?)(?=(?:\s+(?:в|для|на)\b|[?.!,]|$))",
    re.IGNORECASE,
)


def _extract_recipe_reference(message: str) -> dict | None:
    lowered = message.lower()
    if "этот рецепт" in lowered or re.search(r"\bэтот\b", lowered):
        return {"type": "selected", "value": None}

    match = _RECIPE_REF_RE.search(lowered)
    if not match:
        return None
    return {"type": "rank", "value": _ORDINAL_MAP[match.group(1)]}


def _extract_nutrient(message: str) -> str | None:
    lowered = message.lower()
    if "бел" in lowered:
        return "protein"
    if "жир" in lowered:
        return "fat"
    if "углев" in lowered:
        return "carbs"
    if "бжу" in lowered:
        return "bju"
    if "калори" in lowered or "ккал" in lowered:
        return "calories"
    return None


def _extract_target_ingredient(message: str) -> str | None:
    lowered = " ".join(message.lower().split())
    match = _SUBSTITUTION_RE.search(lowered)
    if match:
        return match.group(1).strip()

    without_match = re.search(r"\bбез\s+([а-яёa-z0-9\-%\s]+?)(?=(?:[?.!,]|$))", lowered)
    if without_match:
        return without_match.group(1).strip()
    return None


def _extract_recipe_title_query(message: str, *, nutrient: str | None) -> str | None:
    lowered = " ".join(message.lower().split())
    if nutrient:
        match = _NUTRITION_TITLE_RE.search(lowered)
        if match:
            return match.group(1).strip()

    if any(word in lowered for word in ["покажи", "ингредиент", "как готовить"]):
        match = _DETAILS_TITLE_RE.search(lowered)
        if match:
            return match.group(1).strip()

    return None


class IntentRouter:
    def decide(self, message: str) -> IntentDecision:
        lowered = " ".join(message.lower().split())
        constraints = extract_query_constraints(lowered)
        recipe_reference = _extract_recipe_reference(lowered)
        nutrient = _extract_nutrient(lowered)
        target_ingredient = _extract_target_ingredient(lowered)
        recipe_title_query = _extract_recipe_title_query(lowered, nutrient=nutrient)

        entities = {
            "recipe_reference": recipe_reference,
            "target_ingredient": target_ingredient,
            "nutrient": nutrient,
            "recipe_title_query": recipe_title_query,
            "include_ingredients": constraints.include_ingredients,
            "exclude_ingredients": constraints.exclude_ingredients,
        }

        if any(token in lowered for token in ["похож", "альтернатив", "аналог"]):
            return IntentDecision(
                intent="similar_recipes",
                route="vector_search",
                entities=entities,
                needs_conversation_context=True,
                needs_recipe_fetch=True,
                needs_vector_search=True,
                needs_sql=True,
                needs_llm=False,
            )

        if any(token in lowered for token in ["заменить", "замену", "вместо", "без яйца", "без молока"]):
            return IntentDecision(
                intent="ingredient_substitution",
                route="substitution",
                entities=entities,
                needs_conversation_context=recipe_reference is not None,
                needs_recipe_fetch=True,
                needs_vector_search=False,
                needs_sql=True,
                needs_llm=False,
            )

        if nutrient:
            return IntentDecision(
                intent="nutrition_question",
                route="sql",
                entities=entities,
                needs_conversation_context=recipe_reference is not None,
                needs_recipe_fetch=True,
                needs_vector_search=False,
                needs_sql=True,
                needs_llm=False,
            )

        if recipe_reference and any(
            token in lowered for token in ["покажи", "ингредиент", "шаг", "готовить", "рецепт"]
        ):
            return IntentDecision(
                intent="recipe_details",
                route="conversation_recipe_fetch",
                entities=entities,
                needs_conversation_context=True,
                needs_recipe_fetch=True,
                needs_vector_search=False,
                needs_sql=True,
                needs_llm=False,
            )

        if constraints.allergy_exclusions or (
            constraints.exclude_ingredients and any(token in lowered for token in ["что подойдет", "что можно", "подбери"])
        ):
            return IntentDecision(
                intent="allergy_or_exclusion",
                route="hybrid_search",
                entities=entities,
                needs_conversation_context=False,
                needs_recipe_fetch=False,
                needs_vector_search=True,
                needs_sql=True,
                needs_llm=False,
            )

        if any(
            token in lowered
            for token in ["завтрак", "ужин", "обед", "перекус", "легк", "быстр", "низкокалори", "после тренировки"]
        ):
            return IntentDecision(
                intent="recommend_recipes",
                route="hybrid_search",
                entities=entities,
                needs_conversation_context=False,
                needs_recipe_fetch=False,
                needs_vector_search=True,
                needs_sql=True,
                needs_llm=False,
            )

        if any(
            token in lowered
            for token in ["рецепт", "найди", "покажи", "есть", "приготовить", "что можно"]
        ):
            return IntentDecision(
                intent="search_recipes",
                route="hybrid_search",
                entities=entities,
                needs_conversation_context=False,
                needs_recipe_fetch=False,
                needs_vector_search=True,
                needs_sql=True,
                needs_llm=False,
            )

        return IntentDecision(
            intent="fallback",
            route="no_retrieval",
            entities=entities,
            needs_conversation_context=False,
            needs_recipe_fetch=False,
            needs_vector_search=False,
            needs_sql=False,
            needs_llm=False,
        )
