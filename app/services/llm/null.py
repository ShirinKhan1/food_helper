from __future__ import annotations

from app.services.llm.base import LLMGenerateRequest


class NullLLMClient:
    def generate(self, request: LLMGenerateRequest) -> str:
        raise RuntimeError("LLM is disabled.")
