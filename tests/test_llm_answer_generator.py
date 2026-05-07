from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.schemas.recipe import RecipeCard
from app.services.answer_generator import AnswerGenerator
from app.services.llm.base import LLMGenerateRequest
from app.services.llm.null import NullLLMClient


class FakeSuccessLLM:
    def generate(self, request: LLMGenerateRequest) -> str:
        return "LLM ответ"


class FakeFailingLLM:
    def generate(self, request: LLMGenerateRequest) -> str:
        raise RuntimeError("LLM unavailable")


def _card(rank: int = 1) -> RecipeCard:
    return RecipeCard(
        rank=rank,
        recipe_id=42,
        title="Тестовый рецепт",
        recipe_url="https://example.com/r",
    )


def test_answer_generator_returns_llm_text_on_success() -> None:
    gen = AnswerGenerator(
        llm_client=FakeSuccessLLM(),
        temperature=0.2,
        max_tokens=500,
        num_ctx=4096,
        think=False,
    )
    out = gen.generate_recipe_list_answer(
        user_message="ужин без мяса",
        fallback_answer="fallback",
        recipes=[_card()],
        warnings=[],
    )
    assert out == "LLM ответ"


def test_answer_generator_fallback_on_llm_error() -> None:
    gen = AnswerGenerator(
        llm_client=FakeFailingLLM(),
        temperature=0.2,
        max_tokens=500,
        num_ctx=4096,
        think=False,
    )
    out = gen.generate_recipe_list_answer(
        user_message="ужин без мяса",
        fallback_answer="fallback-текст",
        recipes=[_card()],
        warnings=[],
    )
    assert out == "fallback-текст"


def test_answer_generator_empty_recipes_no_llm_call() -> None:
    gen = AnswerGenerator(
        llm_client=FakeFailingLLM(),
        temperature=0.2,
        max_tokens=500,
        num_ctx=4096,
        think=False,
    )
    out = gen.generate_recipe_list_answer(
        user_message="x",
        fallback_answer="пусто",
        recipes=[],
        warnings=[],
    )
    assert out == "пусто"


def test_answer_generator_null_client_returns_fallback() -> None:
    gen = AnswerGenerator(
        llm_client=NullLLMClient(),
        temperature=0.2,
        max_tokens=500,
        num_ctx=4096,
        think=False,
    )
    out = gen.generate_recipe_list_answer(
        user_message="x",
        fallback_answer="rule-based",
        recipes=[_card()],
        warnings=[],
    )
    assert out == "rule-based"
