from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.orchestrator.intent_router import IntentRouter
from app.orchestrator.query_constraints import extract_query_constraints

CASES_PATH = Path(__file__).with_name("conversation_cases.jsonl")


def _load_cases() -> list[dict]:
    return [
        json.loads(line)
        for line in CASES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


CASES = _load_cases()


def test_eval_set_has_required_shape() -> None:
    categories = {case["category"] for case in CASES}

    assert len(CASES) >= 30
    assert {
        "search_constraints",
        "allergy_filters",
        "general_substitution",
        "recipe_substitution",
        "nutrition_details",
        "similar_recipes",
        "ambiguity",
    }.issubset(categories)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_eval_case_router_and_constraints(case: dict) -> None:
    decision = IntentRouter().decide(case["message"])
    constraints = extract_query_constraints(case["message"])

    assert decision.intent == case["expected_intent"]
    assert decision.route == case["expected_route"]
    if "expected_include" in case:
        assert constraints.include_ingredients == case["expected_include"]
    if "expected_exclude" in case:
        assert constraints.exclude_ingredients == case["expected_exclude"]
    if "expected_allergy" in case:
        assert constraints.allergy_exclusions == case["expected_allergy"]
