"""Validate decision planner JSONL structure and optional IntentRouter sample."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def validate(rows: list[dict], *, expect_n: int | None) -> list[str]:
    errors: list[str] = []
    if expect_n is not None and len(rows) != expect_n:
        errors.append(f"expected {expect_n} rows, got {len(rows)}")
    ids = [r.get("id") for r in rows]
    if None in ids:
        errors.append("some rows missing id")
    if len(ids) != len(set(ids)):
        errors.append("duplicate id values")
    required_top = {"id", "input", "output"}
    for i, r in enumerate(rows):
        if not required_top <= set(r.keys()):
            errors.append(f"row {i}: missing top-level keys")
            continue
        inp, out = r["input"], r["output"]
        for k in ("message", "recent_messages", "conversation_state", "rule_parse"):
            if k not in inp:
                errors.append(f"row {i}: input missing {k}")
        rp = inp.get("rule_parse") or {}
        for k in ("intent", "route", "entities", "constraints"):
            if k not in rp:
                errors.append(f"row {i}: rule_parse missing {k}")
        for k in (
            "schema_version",
            "intent",
            "action",
            "confidence",
            "constraints",
            "requires_clarification",
        ):
            if k not in out:
                errors.append(f"row {i}: output missing {k}")
        if out.get("requires_clarification") and not out.get("clarification"):
            errors.append(f"row {i}: clarification required but null")
    return errors


def compare_router(rows: list[dict], n: int, rng: random.Random) -> tuple[int, int]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app.orchestrator.intent_router import IntentRouter

    router = IntentRouter()
    candidates = [
        r
        for r in rows
        if not r["input"].get("recent_messages") and not r["output"].get("requires_clarification")
    ]
    rng.shuffle(candidates)
    checked = 0
    mism = 0
    for r in candidates[:n]:
        msg = r["input"]["message"]
        gold = r["output"]["intent"]
        d = router.decide(msg)
        checked += 1
        if gold == "ingredient_substitution" and d.intent == "general_substitution":
            mism += 1
            continue
        if gold != d.intent:
            mism += 1
    return checked, mism


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path, nargs="?", default=ROOT / "data" / "food_helper_decision_planner_500.jsonl")
    ap.add_argument("--expect", type=int, default=500)
    ap.add_argument("--compare-router", type=int, default=0)
    ap.add_argument("--rng-seed", type=int, default=42)
    args = ap.parse_args()
    rows = load_rows(args.path)
    errs = validate(rows, expect_n=args.expect)
    if errs:
        print("Validation FAILED:")
        for e in errs:
            print(" ", e)
        raise SystemExit(1)
    print(f"OK: {len(rows)} rows, unique ids, structure valid")
    if args.compare_router:
        rng = random.Random(args.rng_seed)
        c, m = compare_router(rows, args.compare_router, rng)
        print(f"IntentRouter sample: checked={c} mismatches={m}")


if __name__ == "__main__":
    main()
