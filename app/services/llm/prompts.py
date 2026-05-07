from __future__ import annotations

import json
from dataclasses import replace

from app.services.llm.context import LLMAnswerContext

SYSTEM_PROMPT = """
Ты помощник по рецептам внутри Food Helper.

Правила:
- Отвечай по-русски.
- Используй только переданный контекст.
- Не придумывай рецепты, ингредиенты, шаги приготовления, калории и факты.
- Если данных мало, честно скажи, что нужно уточнить.
- Не давай медицинских гарантий.
""".strip()


def truncate_llm_context(
    context: LLMAnswerContext,
    *,
    max_recipes: int,
    max_ingredients: int,
    max_steps: int,
) -> LLMAnswerContext:
    max_r = max(0, max_recipes)
    recipes = list(context.recipes[:max_r])
    detail = context.recipe_detail
    if detail is not None:
        mi, ms = max(0, max_ingredients), max(0, max_steps)
        detail = detail.model_copy(
            update={
                "ingredients": list(detail.ingredients[:mi]),
                "steps": list(detail.steps[:ms]),
            }
        )
    return replace(context, recipes=recipes, recipe_detail=detail)


def build_user_prompt(context: LLMAnswerContext) -> str:
    payload = {
        "scenario": context.scenario,
        "user_message": context.user_message,
        "constraints": context.constraints.model_dump(mode="json") if context.constraints else None,
        "recipes": [recipe.model_dump(mode="json") for recipe in context.recipes],
        "recipe_detail": context.recipe_detail.model_dump(mode="json") if context.recipe_detail else None,
        "nutrition": context.nutrition.model_dump(mode="json") if context.nutrition else None,
        "substitutions": [item.model_dump(mode="json") for item in context.substitutions],
        "warnings": context.warnings,
        "sources": [item.model_dump(mode="json") for item in context.sources],
        "detail_mode": context.detail_mode,
    }
    return (
        "Контекст:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Сформируй короткий, понятный ответ пользователю. "
        "Не добавляй данные, которых нет в контексте."
    )
