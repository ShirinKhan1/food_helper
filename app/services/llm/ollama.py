from __future__ import annotations

import httpx

from app.services.llm.base import LLMGenerateRequest


class OllamaLLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 90.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    def generate(self, request: LLMGenerateRequest) -> str:
        payload = {
            "model": self._model,
            "system": request.system_prompt,
            "prompt": request.user_prompt,
            "stream": False,
            "think": request.think,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
                "num_ctx": request.num_ctx,
            },
        }

        with httpx.Client(timeout=self._timeout_seconds) as client:
            response = client.post(f"{self._base_url}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()

        answer = str(data.get("response") or "").strip()
        if not answer:
            raise RuntimeError("Ollama returned empty response.")

        return answer
