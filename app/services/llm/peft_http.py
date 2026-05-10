from __future__ import annotations

import httpx

from app.services.llm.base import LLMGenerateRequest


class PeftHttpLLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    def generate(self, request: LLMGenerateRequest) -> str:
        payload: dict[str, object] = {
            "model": self._model,
            "system_prompt": request.system_prompt,
            "user_prompt": request.user_prompt,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "num_ctx": request.num_ctx,
            "think": request.think,
            "stop": [],
        }
        with httpx.Client(timeout=self._timeout_seconds) as client:
            response = client.post(f"{self._base_url}/generate", json=payload)
            response.raise_for_status()
            data = response.json()
        answer = str(data.get("response") or "").strip()
        if not answer:
            raise RuntimeError("PEFT model service returned empty response.")
        return answer
