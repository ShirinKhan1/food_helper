from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.core.config import Settings
from app.schemas.chat import IntentDecision
from app.schemas.search import QueryConstraints
from app.services.conversation_state import ConversationSnapshot
from app.services.llm.base import LLMClient, LLMGenerateRequest
from app.services.llm.parser_postcheck import ParserPostcheck
from app.services.llm.query_parser import LLMQueryParser, parsed_from_rules, should_use_llm_auto


class _FakeLLM(LLMClient):
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def generate(self, request: LLMGenerateRequest) -> str:
        return self._payload


def _settings(**over) -> Settings:
    base = Settings.from_env()
    return replace(base, **over)


def test_parsed_from_rules_matches_router_intent() -> None:
    msg = "Найди рецепты с курицей."
    decision = IntentDecision(
        intent="search_recipes",
        route="hybrid_search",
        entities={},
        needs_vector_search=True,
        needs_sql=True,
    )
    qc = QueryConstraints(include_ingredients=["курица"])
    parsed = parsed_from_rules(msg, decision, qc)
    assert parsed.intent == "search_recipes"
    assert parsed.confidence == 1.0
    assert "курица" in parsed.constraints.include_ingredients


def test_schema_rejects_invalid_confidence() -> None:
    from app.schemas.parser import ParsedUserRequest

    with pytest.raises(Exception):
        ParsedUserRequest.model_validate(
            {
                "intent": "fallback",
                "confidence": 2.0,
                "constraints": {},
            }
        )


def test_llm_invalid_json_falls_back() -> None:
    settings = _settings(
        query_parser_mode="llm",
        llm_query_parser_enabled=True,
        llm_query_parser_postcheck_enabled=True,
    )
    parser = LLMQueryParser(
        settings=settings,
        llm_client=_FakeLLM("not json at all"),
        postcheck=ParserPostcheck(),
    )
    decision = IntentDecision(
        intent="search_recipes",
        route="hybrid_search",
        entities={},
        needs_vector_search=True,
        needs_sql=True,
    )
    r = parser.parse(
        message="x",
        rule_decision=decision,
        rule_constraints=QueryConstraints(),
        recent_messages=[],
        conversation_snapshot=ConversationSnapshot(conversation_id="c"),
    )
    assert r.fallback_reason == "parser_invalid_json"
    assert r.parsed.intent == "search_recipes"


def test_llm_markdown_json_stripped() -> None:
    body = {
        "intent": "recommend_recipes",
        "confidence": 0.9,
        "constraints": {"include_ingredients": ["рис"], "meal_type": "dinner"},
        "requires_clarification": False,
        "clarification": None,
    }
    wrapped = "```json\n" + json.dumps(body, ensure_ascii=False) + "\n```"
    settings = _settings(
        query_parser_mode="llm",
        llm_query_parser_enabled=True,
    )
    parser = LLMQueryParser(
        settings=settings,
        llm_client=_FakeLLM(wrapped),
        postcheck=ParserPostcheck(),
    )
    decision = IntentDecision(
        intent="fallback",
        route="no_retrieval",
        entities={},
    )
    r = parser.parse(
        message="легкий ужин",
        rule_decision=decision,
        rule_constraints=QueryConstraints(),
        recent_messages=[],
        conversation_snapshot=ConversationSnapshot(conversation_id="c"),
    )
    assert r.parsed.intent == "recommend_recipes"
    assert r.used_llm is True


def test_auto_skips_simple_query() -> None:
    settings = _settings(query_parser_mode="auto", llm_query_parser_enabled=True)
    parser = LLMQueryParser(
        settings=settings,
        llm_client=_FakeLLM("{}"),
        postcheck=ParserPostcheck(),
    )
    decision = IntentDecision(
        intent="search_recipes",
        route="hybrid_search",
        entities={},
        needs_vector_search=True,
        needs_sql=True,
    )
    r = parser.parse(
        message="Найди рецепты с курицей.",
        rule_decision=decision,
        rule_constraints=QueryConstraints(include_ingredients=["курица"]),
        recent_messages=[],
        conversation_snapshot=ConversationSnapshot(conversation_id="c"),
    )
    assert r.fallback_reason == "parser_auto_skipped_simple_query"
    assert not r.used_llm


def test_should_use_llm_auto_for_fallback() -> None:
    d = IntentDecision(intent="fallback", route="no_retrieval", entities={})
    assert should_use_llm_auto("коротко", d, QueryConstraints()) is True
