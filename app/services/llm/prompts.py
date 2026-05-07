from __future__ import annotations

import json

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
