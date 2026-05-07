from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMGenerateRequest:
    system_prompt: str
    user_prompt: str
    temperature: float = 0.2
    max_tokens: int = 500
    num_ctx: int = 4096
    think: bool = False


class LLMClient(Protocol):
    def generate(self, request: LLMGenerateRequest) -> str:
        ...
