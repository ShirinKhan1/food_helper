from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.llm.base import LLMGenerateRequest
from app.services.llm.ollama import OllamaLLMClient


def test_ollama_client_returns_response_text() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "  Привет  "}
    mock_response.raise_for_status = MagicMock()

    mock_client_instance = MagicMock()
    mock_client_instance.post.return_value = mock_response

    with patch("app.services.llm.ollama.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = mock_client_instance

        client = OllamaLLMClient(base_url="http://localhost:11434", model="qwen3:4b")
        text = client.generate(
            LLMGenerateRequest(
                system_prompt="sys",
                user_prompt="user",
                temperature=0.2,
                max_tokens=100,
                num_ctx=2048,
                think=False,
            )
        )

    assert text == "Привет"
    mock_client_instance.post.assert_called_once()
    args, kwargs = mock_client_instance.post.call_args
    assert args[0] == "http://localhost:11434/api/generate"
    body = kwargs["json"]
    assert body["model"] == "qwen3:4b"
    assert body["system"] == "sys"
    assert body["prompt"] == "user"
    assert body["think"] is False


def test_ollama_client_empty_response_raises() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": ""}
    mock_response.raise_for_status = MagicMock()

    mock_client_instance = MagicMock()
    mock_client_instance.post.return_value = mock_response

    with patch("app.services.llm.ollama.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = mock_client_instance

        client = OllamaLLMClient(base_url="http://localhost:11434", model="m")
        with pytest.raises(RuntimeError, match="empty"):
            client.generate(
                LLMGenerateRequest(system_prompt="s", user_prompt="u"),
            )
