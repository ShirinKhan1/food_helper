from __future__ import annotations

from app.schemas.recipe import RecipeCard
from app.services.answer_generator import AnswerGenerator
from app.services.llm.base import LLMGenerateRequest


class FakeLLMClient:
    def __init__(self, response: str | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[LLMGenerateRequest] = []

    def generate(self, request: LLMGenerateRequest) -> str:
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.response or ""


def _generator(fake: FakeLLMClient, *, mode: str = "auto", enabled: bool = True) -> AnswerGenerator:
    return AnswerGenerator(
        llm_client=fake,
        temperature=0.2,
        max_tokens=500,
        num_ctx=4096,
        think=False,
        llm_enabled=enabled,
        answer_mode=mode,
        llm_postcheck_enabled=True,
        llm_strict_context=True,
        llm_max_answer_chars=2500,
        llm_strip_think_tags=True,
        llm_log_prompts=False,
        llm_log_responses=False,
        llm_min_recipes_for_list_answer=1,
        llm_max_context_recipes=5,
        llm_max_context_ingredients=30,
        llm_max_context_steps=20,
    )


def _card() -> RecipeCard:
    return RecipeCard(rank=1, recipe_id=1, title="Омлет", recipe_url="https://example.com/omelet")


def test_template_mode_never_calls_llm() -> None:
    fake = FakeLLMClient(response="LLM")
    result = _generator(fake, mode="template").generate_recipe_list_answer(
        intent="search_recipes",
        user_message="test",
        fallback_answer="fallback",
        recipes=[_card()],
        warnings=[],
    )
    assert result.answer == "fallback"
    assert fake.calls == []
    assert result.fallback_reason == "answer_mode_template"


def test_timeout_uses_fallback() -> None:
    fake = FakeLLMClient(error=TimeoutError("timeout"))
    result = _generator(fake).generate_recipe_list_answer(
        intent="search_recipes",
        user_message="test",
        fallback_answer="fallback",
        recipes=[_card()],
        warnings=[],
    )
    assert result.answer == "fallback"
    assert result.fallback_reason == "llm_timeout"
