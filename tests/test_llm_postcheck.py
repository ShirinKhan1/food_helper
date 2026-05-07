from __future__ import annotations

from app.schemas.recipe import RecipeCard
from app.schemas.search import QueryConstraints
from app.services.llm.context import LLMAnswerContext
from app.services.llm.postcheck import PostcheckPolicy, validate_llm_answer


def _context(constraints: QueryConstraints | None = None) -> LLMAnswerContext:
    return LLMAnswerContext(
        scenario="recipe_list",
        user_message="test",
        constraints=constraints,
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


def test_postcheck_strips_qwen_style_think_blocks() -> None:
    t = "think"
    answer = f"<{t}>reasoning</{t}>Ответ"
    result = validate_llm_answer(
        answer=answer,
        context=_context(),
        policy=PostcheckPolicy(scenario="recipe_list", strip_think_tags=True),
    )
    assert result.ok is True
    assert result.sanitized_answer == "Ответ"


def test_postcheck_strips_multiple_think_blocks() -> None:
    t = "think"
    answer = f"<{t}>a</{t}>x<{t}>b</{t}>y"
    result = validate_llm_answer(
        answer=answer,
        context=_context(),
        policy=PostcheckPolicy(scenario="recipe_list", strip_think_tags=True),
    )
    assert result.ok is True
    assert result.sanitized_answer == "xy"


def test_postcheck_strips_reasoning_tags() -> None:
    result = validate_llm_answer(
        answer="<reasoning>x</reasoning>OK",
        context=_context(),
        policy=PostcheckPolicy(scenario="recipe_list", strip_think_tags=True),
    )
    assert result.ok is True
    assert result.sanitized_answer == "OK"


def test_postcheck_rejects_unknown_title() -> None:
    result = validate_llm_answer(
        answer="1. Несуществующий рецепт",
        context=_context(),
        policy=PostcheckPolicy(scenario="recipe_list"),
    )
    assert result.ok is False
    assert "hallucinated_recipe" in result.errors


def test_postcheck_allows_exclusion_after_bez() -> None:
    result = validate_llm_answer(
        answer="Подойдут варианты без молока.",
        context=_context(QueryConstraints(exclude_ingredients=["молоко"])),
        policy=PostcheckPolicy(scenario="recipe_list"),
    )
    assert result.ok is True


def test_postcheck_rejects_forbidden_ingredient_in_answer() -> None:
    result = validate_llm_answer(
        answer="Добавьте молоко в тесто.",
        context=_context(QueryConstraints(exclude_ingredients=["молоко"])),
        policy=PostcheckPolicy(scenario="recipe_list"),
    )
    assert result.ok is False
    assert "forbidden_ingredient_mentioned" in result.errors


def test_postcheck_allergy_exclusion_same_as_exclude() -> None:
    result = validate_llm_answer(
        answer="Используйте яйцо для глазури.",
        context=_context(QueryConstraints(allergy_exclusions=["яйцо"])),
        policy=PostcheckPolicy(scenario="recipe_list"),
    )
    assert result.ok is False
    assert "forbidden_ingredient_mentioned" in result.errors


def test_postcheck_skips_forbidden_check_for_substitution() -> None:
    result = validate_llm_answer(
        answer="Вместо молока подойдёт вода.",
        context=LLMAnswerContext(
            scenario="general_substitution",
            user_message="test",
            constraints=QueryConstraints(exclude_ingredients=["молоко"]),
            substitutions=[],
        ),
        policy=PostcheckPolicy(scenario="general_substitution"),
    )
    assert result.ok is True
