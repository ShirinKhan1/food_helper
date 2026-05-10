from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    """Compatible with app LLMGenerateRequest; optional fields for client parity."""

    model: str | None = None
    system_prompt: str = ""
    user_prompt: str
    temperature: float = 0.2
    max_tokens: int = 500
    num_ctx: int = 4096
    think: bool = False
    stop: list[str] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    response: str
    model: str
    base_model: str
    used_adapter: bool = True
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    base_model: str
    adapter_path: str
    adapter_task: str | None = None
    device: str
    dtype: str
    max_input_tokens: int
    load_error: str | None = None
