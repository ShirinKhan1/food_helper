from __future__ import annotations

import traceback
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from model_server.runtime import ModelRuntime, load_runtime, read_adapter_task
from model_server.schemas import GenerateRequest, GenerateResponse, HealthResponse
from model_server.settings import ModelServerSettings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = ModelServerSettings.from_env()
    app.state.settings = settings
    app.state.runtime: ModelRuntime | None = None
    app.state.load_error: str | None = None
    try:
        app.state.runtime = load_runtime(settings)
    except Exception as exc:  # noqa: BLE001 — surface in /health
        app.state.load_error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    yield


app = FastAPI(title="Food Helper model service", lifespan=lifespan)


@app.get("/health")
def health(request: Request) -> HealthResponse:
    settings: ModelServerSettings = request.app.state.settings
    rt: ModelRuntime | None = request.app.state.runtime
    load_error: str | None = request.app.state.load_error
    if rt is not None:
        return HealthResponse(
            status="ok",
            model_loaded=True,
            base_model=settings.base_model,
            adapter_path=settings.adapter_path,
            adapter_task=rt.adapter_task,
            device=rt.resolved_device,
            dtype=rt.resolved_dtype_name,
            max_input_tokens=settings.max_input_tokens,
            load_error=None,
        )
    return HealthResponse(
        status="error",
        model_loaded=False,
        base_model=settings.base_model,
        adapter_path=settings.adapter_path,
        adapter_task=read_adapter_task(Path(settings.adapter_path)),
        device=settings.device,
        dtype=settings.dtype,
        max_input_tokens=settings.max_input_tokens,
        load_error=load_error,
    )


@app.post("/generate")
def generate(request: Request, body: GenerateRequest) -> JSONResponse | GenerateResponse:
    rt: ModelRuntime | None = request.app.state.runtime
    if rt is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "model_not_loaded", "error": request.app.state.load_error},
        )
    settings = rt.settings
    try:
        text, latency_ms, prompt_tokens, completion_tokens = rt.generate(body)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=500,
            content={"detail": "generation_failed", "error": f"{type(exc).__name__}: {exc}"},
        )
    if not text:
        return JSONResponse(status_code=500, content={"detail": "empty_response"})
    return GenerateResponse(
        response=text,
        model=settings.model_name,
        base_model=settings.base_model,
        used_adapter=True,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


# Optional: expose settings for tests
def create_app() -> FastAPI:
    return app
