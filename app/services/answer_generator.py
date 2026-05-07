from __future__ import annotations

import json

from app.schemas.recipe import RecipeCard
from app.services.llm.base import LLMClient, LLMGenerateRequest
from app.services.llm.null import NullLLMClient


SYSTEM_PROMPT = """
Ты помощник по рецептам внутри Food Helper.

Правила:
- Отвечай по-русски.
- Используй только переданный контекст.
- Не придумывай рецепты, ингредиенты, калории и факты, которых нет в контексте.
- Если данных мало, честно скажи, что можно уточнить.
- Ответ должен быть коротким, полезным и дружелюбным.
- Не давай медицинских гарантий по аллергиям.
""".strip()


class AnswerGenerator:
    def __init__(
        self,
        *,
        llm_client: LLMClient,
        temperature: float,
        max_tokens: int,
        num_ctx: int,
        think: bool,
    ) -> None:
        self._llm_client = llm_client
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._num_ctx = num_ctx
        self._think = think

    def generate_recipe_list_answer(
        self,
        *,
        user_message: str,
        fallback_answer: str,
        recipes: list[RecipeCard],
        warnings: list[str],
    ) -> str:
        if not recipes:
            return fallback_answer

        if isinstance(self._llm_client, NullLLMClient):
            return fallback_answer

        context = {
            "recipes": [recipe.model_dump(mode="json") for recipe in recipes],
            "warnings": warnings,
        }

        prompt = f"""
Запрос пользователя:
{user_message}

Найденные рецепты и ограничения:
{json.dumps(context, ensure_ascii=False, indent=2)}

Сформулируй ответ:
- сначала коротко скажи, что нашёл;
- перечисли только рецепты из списка;
- для каждого варианта дай 1 короткую причину, почему он может подойти;
- если есть предупреждения, аккуратно добавь их в конце;
- не добавляй новые рецепты, ингредиенты или значения КБЖУ.
""".strip()

        try:
            return self._llm_client.generate(
                LLMGenerateRequest(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=prompt,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    num_ctx=self._num_ctx,
                    think=self._think,
                )
            )
        except Exception:
            return fallback_answer
