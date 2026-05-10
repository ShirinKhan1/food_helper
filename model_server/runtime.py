from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from model_server.schemas import GenerateRequest

if TYPE_CHECKING:
    from model_server.settings import ModelServerSettings

_t = "think"
_THINK_BLOCK_RES = (
    re.compile(rf"<{_t}>.*?</{_t}>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<reasoning>.*?</reasoning>", re.IGNORECASE | re.DOTALL),
)


def strip_think_blocks(text: str) -> str:
    out = text
    while True:
        prev = out
        for pattern in _THINK_BLOCK_RES:
            out = pattern.sub("", out)
        if out == prev:
            break
    return out


def read_adapter_task(adapter_path: Path) -> str | None:
    meta = adapter_path / "food_helper_metadata.json"
    if not meta.is_file():
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        task = data.get("task")
        return str(task) if task else None
    except Exception:
        return None


def _resolve_device(device_setting: str) -> str:
    d = device_setting.lower()
    if d == "cpu":
        return "cpu"
    if d == "cuda":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def _resolve_dtype(device: str, dtype_setting: str) -> torch.dtype:
    ds = dtype_setting.lower()
    if ds == "float32":
        return torch.float32
    if ds == "float16":
        return torch.float16
    if ds == "bfloat16":
        return torch.bfloat16
    if device == "cuda":
        if torch.cuda.is_bf16_supported():
            return torch.bfloat16
        return torch.float16
    return torch.float32


class ModelRuntime:
    def __init__(
        self,
        *,
        tokenizer: Any,
        model: Any,
        settings: ModelServerSettings,
        adapter_task: str | None,
        resolved_device: str,
        resolved_dtype_name: str,
    ) -> None:
        self._tokenizer = tokenizer
        self._model = model
        self._settings = settings
        self.adapter_task = adapter_task
        self.resolved_device = resolved_device
        self.resolved_dtype_name = resolved_dtype_name

    @property
    def settings(self) -> ModelServerSettings:
        return self._settings

    def _model_device(self) -> torch.device:
        return next(self._model.parameters()).device

    def generate(self, request: GenerateRequest) -> tuple[str, int, int, int]:
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.user_prompt})

        tmpl_kwargs: dict[str, Any] = {
            "tokenize": False,
            "add_generation_prompt": True,
        }
        try:
            text = self._tokenizer.apply_chat_template(
                messages,
                **tmpl_kwargs,
                enable_thinking=request.think,
            )
        except TypeError:
            text = self._tokenizer.apply_chat_template(messages, **tmpl_kwargs)

        max_len = min(request.num_ctx, self._settings.max_input_tokens)
        inputs = self._tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=max_len,
        )
        device = self._model_device()
        inputs = {k: v.to(device) for k, v in inputs.items()}

        pad_id = self._tokenizer.pad_token_id or self._tokenizer.eos_token_id
        gen_kwargs: dict[str, Any] = {
            "max_new_tokens": request.max_tokens,
            "pad_token_id": pad_id,
            "eos_token_id": self._tokenizer.eos_token_id,
        }
        if request.temperature and request.temperature > 0:
            gen_kwargs["do_sample"] = True
            gen_kwargs["temperature"] = max(float(request.temperature), 1e-5)
        else:
            gen_kwargs["do_sample"] = False

        t0 = time.perf_counter()
        prompt_len = int(inputs["input_ids"].shape[-1])
        with torch.inference_mode():
            output_ids = self._model.generate(**inputs, **gen_kwargs)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        new_tokens = output_ids[0][prompt_len:]
        raw = self._tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        out = strip_think_blocks(raw).strip()
        completion_len = int(new_tokens.shape[-1])
        return out, latency_ms, prompt_len, completion_len


def load_runtime(settings: ModelServerSettings) -> ModelRuntime:
    adapter_path = Path(settings.adapter_path)
    if not adapter_path.is_dir():
        raise FileNotFoundError(f"Adapter path is not a directory: {adapter_path}")

    tokenizer_source = str(adapter_path) if settings.use_adapter_tokenizer else settings.base_model
    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_source,
        local_files_only=settings.local_files_only_adapter and settings.use_adapter_tokenizer,
        trust_remote_code=False,
    )

    resolved_device = _resolve_device(settings.device)
    torch_dtype = _resolve_dtype(resolved_device, settings.dtype)
    dtype_name = str(torch_dtype).replace("torch.", "")

    model_kwargs: dict[str, Any] = {
        "torch_dtype": torch_dtype,
        "trust_remote_code": False,
    }
    if resolved_device == "cuda":
        model_kwargs["device_map"] = "auto"
    else:
        model_kwargs["device_map"] = None

    base = AutoModelForCausalLM.from_pretrained(settings.base_model, **model_kwargs)
    if resolved_device == "cpu":
        base = base.to("cpu")

    model = PeftModel.from_pretrained(
        base,
        str(adapter_path),
        is_trainable=False,
        local_files_only=settings.local_files_only_adapter,
    )
    model.eval()
    adapter_task = read_adapter_task(adapter_path)

    return ModelRuntime(
        tokenizer=tokenizer,
        model=model,
        settings=settings,
        adapter_task=adapter_task,
        resolved_device=resolved_device,
        resolved_dtype_name=dtype_name,
    )
