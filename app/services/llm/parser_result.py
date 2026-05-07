from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.parser import ParsedUserRequest


class QueryParserResult(BaseModel):
    parsed: ParsedUserRequest
    used_llm: bool = False
    fallback_reason: str | None = None
    latency_ms: int | None = None
    prompt_chars: int | None = None
    response_chars: int | None = None
    postcheck_passed: bool | None = None
    postcheck_errors: list[str] = Field(default_factory=list)
