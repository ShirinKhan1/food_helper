from __future__ import annotations

import pytest

from app.schemas.parser import ClarificationRequest, ParsedQueryConstraints, ParsedUserRequest, RecipeReference
from app.schemas.search import QueryConstraints
from app.services.conversation_state import ConversationSnapshot
from app.services.llm.parser_postcheck import ParserPostcheck


def _snap(**kwargs) -> ConversationSnapshot:
    return ConversationSnapshot(conversation_id="c1", **kwargs)


def test_postcheck_ok_minimal() -> None:
    pc = ParserPostcheck()
    parsed = ParsedUserRequest(
        intent="search_recipes",
        confidence=0.9,
        constraints=ParsedQueryConstraints(),
    )
    r = pc.validate(parsed, rule_constraints=QueryConstraints(), snapshot=_snap())
    assert r.ok and r.sanitized is not None


def test_postcheck_rejects_bad_nutrient() -> None:
    pc = ParserPostcheck()
    parsed = ParsedUserRequest(
        intent="nutrition_question",
        confidence=0.9,
        nutrients=["sodium"],
        constraints=ParsedQueryConstraints(),
    )
    r = pc.validate(parsed, rule_constraints=QueryConstraints(), snapshot=_snap())
    assert not r.ok


def test_postcheck_clarification_requires_question() -> None:
    pc = ParserPostcheck()
    parsed = ParsedUserRequest(
        intent="recommend_recipes",
        confidence=0.9,
        requires_clarification=True,
        clarification=None,
        constraints=ParsedQueryConstraints(),
    )
    r = pc.validate(parsed, rule_constraints=QueryConstraints(), snapshot=_snap())
    assert not r.ok


def test_postcheck_clarification_false_must_null_clarification() -> None:
    pc = ParserPostcheck()
    parsed = ParsedUserRequest(
        intent="search_recipes",
        confidence=0.9,
        requires_clarification=False,
        clarification=ClarificationRequest(reason="x", question="q?"),
        constraints=ParsedQueryConstraints(),
    )
    r = pc.validate(parsed, rule_constraints=QueryConstraints(), snapshot=_snap())
    assert not r.ok


def test_postcheck_preserves_rule_allergy() -> None:
    pc = ParserPostcheck()
    rules = QueryConstraints(allergy_exclusions=["молоко"])
    parsed = ParsedUserRequest(
        intent="allergy_or_exclusion",
        confidence=0.9,
        constraints=ParsedQueryConstraints(allergy_exclusions=[]),
    )
    r = pc.validate(parsed, rule_constraints=rules, snapshot=_snap())
    assert not r.ok


def test_postcheck_rank_out_of_range_without_clarification() -> None:
    pc = ParserPostcheck()
    parsed = ParsedUserRequest(
        intent="nutrition_question",
        confidence=0.9,
        recipe_reference=RecipeReference(type="rank", value=5),
        nutrients=["protein"],
        constraints=ParsedQueryConstraints(),
    )
    r = pc.validate(
        parsed,
        rule_constraints=QueryConstraints(),
        snapshot=_snap(last_recipe_results=[1, 2]),
    )
    assert not r.ok


def test_postcheck_rank_out_of_range_allowed_with_clarification() -> None:
    pc = ParserPostcheck()
    parsed = ParsedUserRequest(
        intent="nutrition_question",
        confidence=0.9,
        requires_clarification=True,
        clarification=ClarificationRequest(reason="ctx", question="Какой рецепт?"),
        recipe_reference=RecipeReference(type="rank", value=5),
        nutrients=["protein"],
        constraints=ParsedQueryConstraints(),
    )
    r = pc.validate(
        parsed,
        rule_constraints=QueryConstraints(),
        snapshot=_snap(last_recipe_results=[1, 2]),
    )
    assert r.ok


@pytest.mark.parametrize(
    "text",
    [
        "select * from recipes",
        "https://evil.com",
    ],
)
def test_postcheck_rejects_sql_or_url(text: str) -> None:
    pc = ParserPostcheck()
    parsed = ParsedUserRequest(
        intent="search_recipes",
        confidence=0.9,
        search_query=text,
        constraints=ParsedQueryConstraints(),
    )
    r = pc.validate(parsed, rule_constraints=QueryConstraints(), snapshot=_snap())
    assert not r.ok
