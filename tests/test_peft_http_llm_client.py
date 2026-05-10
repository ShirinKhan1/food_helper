from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.services.container import build_llm_client
from app.services.llm.base import LLMGenerateRequest
from app.services.llm.peft_http import PeftHttpLLMClient


def test_peft_http_client_success() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "  {\"intent\": \"search_recipes\"}  "}
    mock_response.raise_for_status = MagicMock()

    mock_client_instance = MagicMock()
    mock_client_instance.post.return_value = mock_response

    with patch("app.services.llm.peft_http.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = mock_client_instance

        client = PeftHttpLLMClient(
            base_url="http://model:8010",
            model="food-helper-qwen3-0.6b-lora",
            timeout_seconds=15.0,
        )
        text = client.generate(
            LLMGenerateRequest(
                system_prompt="sys",
                user_prompt="user",
                temperature=0.0,
                max_tokens=700,
                num_ctx=4096,
                think=False,
            )
        )

    assert text == '{"intent": "search_recipes"}'
    mock_client_instance.post.assert_called_once()
    args, kwargs = mock_client_instance.post.call_args
    assert args[0] == "http://model:8010/generate"
    body = kwargs["json"]
    assert body["model"] == "food-helper-qwen3-0.6b-lora"
    assert body["system_prompt"] == "sys"
    assert body["user_prompt"] == "user"
    assert body["think"] is False


def test_peft_http_client_empty_response_raises() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": ""}
    mock_response.raise_for_status = MagicMock()

    mock_client_instance = MagicMock()
    mock_client_instance.post.return_value = mock_response

    with patch("app.services.llm.peft_http.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = mock_client_instance

        client = PeftHttpLLMClient(base_url="http://localhost:8010", model="m")
        with pytest.raises(RuntimeError, match="empty"):
            client.generate(LLMGenerateRequest(system_prompt="s", user_prompt="u"))


def test_peft_http_client_http_error_raises() -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("503")

    mock_client_instance = MagicMock()
    mock_client_instance.post.return_value = mock_response

    with patch("app.services.llm.peft_http.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = mock_client_instance

        client = PeftHttpLLMClient(base_url="http://localhost:8010", model="m")
        with pytest.raises(Exception, match="503"):
            client.generate(LLMGenerateRequest(system_prompt="s", user_prompt="u"))


def test_build_llm_client_peft_http() -> None:
    c = build_llm_client(
        provider="peft_http",
        base_url="http://model:8010",
        model="food-helper-qwen3-0.6b-lora",
        timeout_seconds=12.0,
    )
    assert isinstance(c, PeftHttpLLMClient)


def test_build_llm_client_none_unknown() -> None:
    assert build_llm_client(provider="none", base_url="http://x", model="m", timeout_seconds=1.0) is None
    assert build_llm_client(provider="unknown", base_url="http://x", model="m", timeout_seconds=1.0) is None


def test_settings_parser_base_url_fallback() -> None:
    s = Settings.from_env()
    # resolved URL should be non-empty string
    assert s.llm_query_parser_resolved_base_url
