from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.schemas.recipe import RecipeCard, SourceInfo, SubstitutionOption
from app.schemas.search import QueryConstraints
from app.services.answer_generator import AnswerGenerator
from app.services.llm.base import LLMGenerateRequest
from app.services.llm.null import NullLLMClient
from tests.evals.test_rag_scenarios import InMemoryRecipeRepository


class FakeSuccessLLM:
    def __init__(self, response: str = "LLM ответ") -> None:
        self.response = response

    def generate(self, request: LLMGenerateRequest) -> str:
        return self.response


class FakeFailingLLM:
    def generate(self, request: LLMGenerateRequest) -> str:
        raise RuntimeError("LLM unavailable")


class FakeRecordingLLM:
    def __init__(self, response: str = "LLM ответ") -> None:
        self.response = response
        self.requests: list[LLMGenerateRequest] = []

    def generate(self, request: LLMGenerateRequest) -> str:
        self.requests.append(request)
        return self.response


def _generator_postcheck_off(llm: FakeSuccessLLM | FakeRecordingLLM) -> AnswerGenerator:
    return AnswerGenerator(
        llm_client=llm,
        temperature=0.2,
        max_tokens=500,
        num_ctx=4096,
        think=False,
        llm_enabled=True,
        answer_mode="llm",
        llm_postcheck_enabled=False,
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


def _apple_pie_detail():
    repo = InMemoryRecipeRepository()
    row = repo.get_recipe_row_by_id(3)
    assert row is not None
    return repo.row_to_recipe_detail(row)


def _card(rank: int = 1, recipe_id: int = 42, title: str = "Тестовый рецепт") -> RecipeCard:
    return RecipeCard(
        rank=rank,
        recipe_id=recipe_id,
        title=title,
        recipe_url="https://example.com/r",
    )


def test_answer_generator_returns_llm_text_on_success() -> None:
    gen = AnswerGenerator(
        llm_client=FakeSuccessLLM(),
        temperature=0.2,
        max_tokens=500,
        num_ctx=4096,
        think=False,
        llm_enabled=True,
        answer_mode="auto",
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
    out = gen.generate_recipe_list_answer(
        intent="search_recipes",
        user_message="ужин без мяса",
        fallback_answer="fallback",
        recipes=[_card()],
        warnings=[],
    )
    assert out.answer == "LLM ответ"
    assert out.used_llm is True


def test_answer_generator_fallback_on_llm_error() -> None:
    gen = AnswerGenerator(
        llm_client=FakeFailingLLM(),
        temperature=0.2,
        max_tokens=500,
        num_ctx=4096,
        think=False,
        llm_enabled=True,
        answer_mode="auto",
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
    out = gen.generate_recipe_list_answer(
        intent="search_recipes",
        user_message="ужин без мяса",
        fallback_answer="fallback-текст",
        recipes=[_card()],
        warnings=[],
    )
    assert out.answer == "fallback-текст"
    assert out.fallback_reason == "llm_exception"


def test_answer_generator_empty_recipes_no_llm_call() -> None:
    gen = AnswerGenerator(
        llm_client=FakeFailingLLM(),
        temperature=0.2,
        max_tokens=500,
        num_ctx=4096,
        think=False,
        llm_enabled=True,
        answer_mode="auto",
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
    out = gen.generate_recipe_list_answer(
        intent="search_recipes",
        user_message="x",
        fallback_answer="пусто",
        recipes=[],
        warnings=[],
    )
    assert out.answer == "пусто"
    assert out.fallback_reason == "no_context"


def test_answer_generator_null_client_returns_fallback() -> None:
    gen = AnswerGenerator(
        llm_client=NullLLMClient(),
        temperature=0.2,
        max_tokens=500,
        num_ctx=4096,
        think=False,
        llm_enabled=True,
        answer_mode="auto",
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
    out = gen.generate_recipe_list_answer(
        intent="search_recipes",
        user_message="x",
        fallback_answer="rule-based",
        recipes=[_card()],
        warnings=[],
    )
    assert out.answer == "rule-based"
    assert out.fallback_reason == "llm_client_null"


def test_answer_generator_rejects_hallucinated_title() -> None:
    gen = AnswerGenerator(
        llm_client=FakeSuccessLLM("1. Несуществующий рецепт"),
        temperature=0.2,
        max_tokens=500,
        num_ctx=4096,
        think=False,
        llm_enabled=True,
        answer_mode="auto",
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
    out = gen.generate_recipe_list_answer(
        intent="search_recipes",
        user_message="x",
        fallback_answer="rule-based",
        recipes=[_card()],
        warnings=[],
    )
    assert out.answer == "rule-based"
    assert out.fallback_reason == "postcheck_hallucinated_recipe"


def test_answer_generator_skips_llm_when_below_min_recipes() -> None:
    class CountingLLM:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, request: LLMGenerateRequest) -> str:
            self.calls += 1
            return "LLM"

    llm = CountingLLM()
    gen = AnswerGenerator(
        llm_client=llm,
        temperature=0.2,
        max_tokens=500,
        num_ctx=4096,
        think=False,
        llm_enabled=True,
        answer_mode="auto",
        llm_postcheck_enabled=True,
        llm_strict_context=True,
        llm_max_answer_chars=2500,
        llm_strip_think_tags=True,
        llm_log_prompts=False,
        llm_log_responses=False,
        llm_min_recipes_for_list_answer=2,
        llm_max_context_recipes=5,
        llm_max_context_ingredients=30,
        llm_max_context_steps=20,
    )
    out = gen.generate_recipe_list_answer(
        intent="search_recipes",
        user_message="x",
        fallback_answer="rule-based",
        recipes=[_card()],
        warnings=[],
    )
    assert llm.calls == 0
    assert out.answer == "rule-based"
    assert out.fallback_reason == "no_context"


def test_llm_recipe_detail_answer_uses_llm() -> None:
    llm = FakeSuccessLLM("Детальный ответ")
    gen = _generator_postcheck_off(llm)
    detail = _apple_pie_detail()
    out = gen.generate_recipe_detail_answer(
        user_message="Покажи рецепт",
        fallback_answer="fallback",
        detail=detail,
        warnings=[],
    )
    assert out.used_llm is True
    assert out.answer == "Детальный ответ"
    assert out.postcheck_passed is None


def test_llm_nutrition_answer_uses_llm() -> None:
    llm = FakeSuccessLLM("БЖУ ответ")
    gen = _generator_postcheck_off(llm)
    detail = _apple_pie_detail()
    nutrition = detail.nutrition
    out = gen.generate_nutrition_answer(
        user_message="Сколько калорий?",
        fallback_answer="fallback",
        nutrition=nutrition,
        detail=detail,
        warnings=[],
    )
    assert out.used_llm is True
    assert out.answer == "БЖУ ответ"


def test_llm_nutrition_candidates_answer_uses_llm() -> None:
    llm = FakeSuccessLLM("Кандидаты")
    gen = _generator_postcheck_off(llm)
    out = gen.generate_nutrition_candidates_answer(
        intent="nutrition_question",
        user_message="Сколько калорий?",
        fallback_answer="fallback",
        recipes=[_card(rank=1), _card(rank=2, recipe_id=43, title="Второй")],
        warnings=[],
    )
    assert out.used_llm is True
    assert out.answer == "Кандидаты"


def test_llm_substitution_answer_uses_llm() -> None:
    llm = FakeSuccessLLM("Замена")
    gen = _generator_postcheck_off(llm)
    detail = _apple_pie_detail()
    subs = [SubstitutionOption(name="мёд", note="по вкусу")]
    out = gen.generate_substitution_answer(
        user_message="Заменить сахар",
        fallback_answer="fallback",
        detail=detail,
        substitutions=subs,
        warnings=[],
    )
    assert out.used_llm is True
    assert out.answer == "Замена"


def test_llm_general_substitution_answer_uses_llm() -> None:
    llm = FakeSuccessLLM("Общая замена")
    gen = _generator_postcheck_off(llm)
    subs = [SubstitutionOption(name="кленовый сироп", note=None)]
    out = gen.generate_general_substitution_answer(
        user_message="На что заменить сахар?",
        fallback_answer="fallback",
        substitutions=subs,
        warnings=[],
    )
    assert out.used_llm is True
    assert out.answer == "Общая замена"


def test_llm_recipe_detail_passes_constraints_into_prompt() -> None:
    llm = FakeRecordingLLM()
    gen = _generator_postcheck_off(llm)
    detail = _apple_pie_detail()
    constraints = QueryConstraints(exclude_ingredients=["мясо"])
    gen.generate_recipe_detail_answer(
        user_message="Покажи рецепт",
        fallback_answer="fallback",
        detail=detail,
        warnings=[],
        constraints=constraints,
        sources=[SourceInfo(type="recipe", recipe_id=detail.recipe_id, title=detail.title, url=detail.recipe_url)],
    )
    assert len(llm.requests) == 1
    assert "мясо" in llm.requests[0].user_prompt
