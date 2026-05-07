from __future__ import annotations

import json
from pathlib import Path

from app.schemas.chat import ChatRequest
from tests.evals.test_rag_scenarios import InMemoryConversationStateService, build_pipeline

CASES_FILE = Path("tests/eval_cases/chat_llm_answer_cases.jsonl")


def run() -> int:
    state = InMemoryConversationStateService()
    pipeline = build_pipeline(state)

    passed = 0
    total = 0
    for line in CASES_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        total += 1
        case = json.loads(line)
        response = pipeline.handle_chat(
            ChatRequest(
                conversation_id=f"eval-{total}",
                message=case["message"],
                options={"include_debug": True},
            )
        )
        data = response.model_dump(mode="json")
        answer = (data.get("answer") or "").lower()
        ok = bool(data.get("answer"))
        if case.get("expected_intent") and data.get("intent") != case["expected_intent"]:
            ok = False
        if case.get("expected_route") and data.get("route") != case["expected_route"]:
            ok = False
        if case.get("expected_intent_any") and data.get("intent") not in case["expected_intent_any"]:
            ok = False
        if case.get("must_not_say_medically_safe") and "безопасно" in answer:
            ok = False
        if case.get("must_include_units") and ("ккал" not in answer and " г" not in answer):
            ok = False
        if case.get("must_not_hallucinate_recipe") and data.get("recipes"):
            known = {item["title"].lower() for item in data["recipes"]}
            for line_text in answer.splitlines():
                if ". " in line_text:
                    candidate = line_text.split(". ", 1)[1].split("—", 1)[0].strip()
                    if candidate and candidate not in known:
                        ok = False
                        break
        if ok:
            passed += 1
        print(f"[{'PASS' if ok else 'FAIL'}] {case['message']}")
    print(f"Summary: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(run())
