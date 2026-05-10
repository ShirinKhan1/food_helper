from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelServerSettings:
    base_model: str
    adapter_path: str
    model_name: str
    device: str
    dtype: str
    max_input_tokens: int
    enable_thinking_default: bool
    use_adapter_tokenizer: bool
    local_files_only_adapter: bool
    host: str
    port: int

    @classmethod
    def from_env(cls) -> "ModelServerSettings":
        return cls(
            base_model=os.getenv("MODEL_BASE_NAME", "Qwen/Qwen3-0.6B"),
            adapter_path=os.getenv("MODEL_ADAPTER_PATH", "/opt/models/food_helper_lora_adapter"),
            model_name=os.getenv("MODEL_NAME", "food-helper-qwen3-0.6b-lora"),
            device=os.getenv("MODEL_DEVICE", "auto").lower(),
            dtype=os.getenv("MODEL_DTYPE", "auto").lower(),
            max_input_tokens=int(os.getenv("MODEL_MAX_INPUT_TOKENS", "4096")),
            enable_thinking_default=os.getenv("MODEL_ENABLE_THINKING_DEFAULT", "false").lower()
            == "true",
            use_adapter_tokenizer=os.getenv("MODEL_USE_ADAPTER_TOKENIZER", "true").lower()
            == "true",
            local_files_only_adapter=os.getenv("MODEL_ADAPTER_LOCAL_FILES_ONLY", "true").lower()
            == "true",
            host=os.getenv("MODEL_SERVER_HOST", "0.0.0.0"),
            port=int(os.getenv("MODEL_SERVER_PORT", "8010")),
        )
