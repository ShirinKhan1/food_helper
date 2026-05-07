#!/usr/bin/env python3
"""Offline eval for query parser rules baseline (IntentRouter + parsed_from_rules).

Usage:
  python scripts/eval/run_query_parser_eval.py

With live LLM (optional):
  set QUERY_PARSER_MODE=llm LLM_QUERY_PARSER_ENABLED=true and ensure Ollama — not covered by default CI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.orchestrator.intent_router import IntentRouter
from app.orchestrator.query_constraints import extract_query_constraints
from app.services.conversation_state import ConversationSnapshot
from app.services.llm.query_parser import LLMQueryParser, parsed_from_rules
from app.core.config import Settings
from app.services.llm.parser_postcheck import ParserPostcheck


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=ROOT / "tests" / "eval_cases" / "query_parser_cases.jsonl",
    )
    args = parser.parse_args()

    router = IntentRouter()
    settings = Settings.from_env()
    llm_parser = LLMQueryParser(settings=settings, llm_client=None, postcheck=ParserPostcheck())

    failed = 0
    total = 0
    with args.cases.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            case = json.loads(line)
            msg = case["message"]
            exp = case.get("expected") or {}
            snap_data = case.get("state") or {}
            snapshot = ConversationSnapshot(
                conversation_id="eval",
                last_recipe_results=list(snap_data.get("last_recipe_results") or []),
                selected_recipe_id=snap_data.get("selected_recipe_id"),
            )

            if case.get("check") == "rules":
                decision = router.decide(msg)
                qc = extract_query_constraints(msg)
                parsed = parsed_from_rules(msg, decision, qc)
                if exp.get("intent") and parsed.intent != exp["intent"]:
                    print(f"FAIL id={case.get('id')}: intent want={exp['intent']} got={parsed.intent} msg={msg!r}")
                    failed += 1
                    continue
                if "requires_clarification" in exp and parsed.requires_clarification != exp["requires_clarification"]:
                    print(f"FAIL id={case.get('id')}: clarification flag msg={msg!r}")
                    failed += 1
                    continue
                pr = llm_parser.parse(
                    message=msg,
                    rule_decision=decision,
                    rule_constraints=qc,
                    recent_messages=[],
                    conversation_snapshot=snapshot,
                )
                if pr.parsed.intent != parsed.intent:
                    print(f"FAIL id={case.get('id')}: parser drift msg={msg!r}")
                    failed += 1

    print(f"eval_cases: total={total} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
