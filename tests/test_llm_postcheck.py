from __future__ import annotations

from app.schemas.recipe import RecipeCard
from app.services.llm.context import LLMAnswerContext
from app.services.llm.postcheck import PostcheckPolicy, validate_llm_answer


def _context() -> LLMAnswerContext:
    return LLMAnswerContext(
        scenario="recipe_list",
        user_message="test",
        recipes=[
            RecipeCard(rank=1, recipe_id=1, title="Омлет", recipe_url="https://example.com/omelet"),
        ],
    )


def test_postcheck_rejects_empty_answer() -> None:
    result = validate_llm_answer(answer="   ", context=_context(), policy=PostcheckPolicy(scenario="recipe_list"))
    assert result.ok is False
    assert "empty_answer" in result.errors


def test_postcheck_strips_think_tags() -> None:
    result = validate_llm_answer(
        answer="<think>hidden</think>Готово",
        context=_context(),
        policy=PostcheckPolicy(scenario="recipe_list", strip_think_tags=True),
    )
    assert result.ok is True
    assert result.sanitized_answer == "Готово"


def test_postcheck_rejects_unknown_title() -> None:
    result = validate_llm_answer(
        answer="1. Несуществующий рецепт",
        context=_context(),
        policy=PostcheckPolicy(scenario="recipe_list"),
    )
    assert result.ok is False
    assert "hallucinated_recipe" in result.errors
