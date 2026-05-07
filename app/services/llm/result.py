from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AnswerGenerationResult:
    answer: str
    used_llm: bool
    fallback_reason: str | None = None
    latency_ms: int | None = None
    prompt_chars: int | None = None
    response_chars: int | None = None
    postcheck_passed: bool | None = None
    postcheck_errors: list[str] = field(default_factory=list)
