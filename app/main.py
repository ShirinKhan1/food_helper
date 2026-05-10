from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx

from app.api.routes_auth import router as auth_router
from app.api.routes_chat import router as chat_router
from app.api.routes_chats import router as chats_router
from app.api.routes_debug import router as debug_router
from app.api.routes_recipes import router as recipes_router
from app.core.config import Settings
from app.core.db import DatabaseUnavailableError
from app.core.db_schema_bootstrap import ensure_schema
from app.services.container import AppServices, build_services


def create_app(
    *,
    settings: Settings | None = None,
    services: AppServices | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_services = services or build_services(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.services = resolved_services
        ensure_schema(resolved_services.db)
        try:
            resolved_services.embedding_service.maybe_preload()
        except Exception:
            # The embedding model is optional at startup and can still be loaded lazily.
            pass
        yield

    app = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)
    app.state.services = resolved_services

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved_settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(chats_router)
    app.include_router(chat_router)
    app.include_router(debug_router)
    app.include_router(recipes_router)

    @app.get("/health")
    def health() -> dict[str, object]:
        try:
            db_status = resolved_services.db.ping()
        except DatabaseUnavailableError:
            db_status = "error"

        llm_block = _llm_health_block(resolved_settings)

        core_ok = db_status == "ok"
        degraded_parser = (
            llm_block["parser_health"] == "error"
            and resolved_settings.llm_query_parser_enabled
            and resolved_settings.query_parser_mode in {"llm", "auto"}
        )
        degraded_answer = (
            llm_block["answer_health"] == "error"
            and resolved_settings.llm_enabled
            and resolved_settings.answer_mode in {"llm", "auto"}
        )
        status = "ok"
        if not core_ok:
            status = "degraded"
        elif degraded_parser or degraded_answer:
            status = "degraded"

        return {
            "status": status,
            "db": db_status,
            "embedding_model": resolved_services.embedding_service.health_status(),
            "llm": llm_block,
        }

    return app


def _llm_health_block(settings: Settings) -> dict[str, str]:
    parser_provider = settings.llm_query_parser_provider
    parser_model = settings.llm_query_parser_model
    if not settings.llm_query_parser_enabled or settings.query_parser_mode == "rules":
        parser_health = "disabled"
    else:
        parser_health = _probe_llm_upstream(
            provider=parser_provider,
            base_url=settings.llm_query_parser_resolved_base_url,
        )

    answer_provider = settings.llm_provider
    answer_model = settings.llm_model
    if not settings.llm_enabled or answer_provider == "none":
        answer_health = "disabled"
    else:
        answer_health = _probe_llm_upstream(
            provider=answer_provider,
            base_url=settings.llm_base_url.rstrip("/"),
        )

    return {
        "parser_provider": parser_provider,
        "parser_model": parser_model,
        "parser_health": parser_health,
        "answer_provider": answer_provider,
        "answer_model": answer_model,
        "answer_health": answer_health,
    }


def _probe_llm_upstream(*, provider: str, base_url: str) -> str:
    base = base_url.rstrip("/")
    try:
        if provider == "peft_http":
            r = httpx.get(f"{base}/health", timeout=2.0)
            if not r.is_success:
                return "error"
            data = r.json()
            if isinstance(data, dict) and data.get("model_loaded") is False:
                return "error"
            return "ok"
        if provider == "ollama":
            r = httpx.get(f"{base}/api/tags", timeout=2.0)
            return "ok" if r.is_success else "error"
    except Exception:
        return "error"
    return "error"


app = create_app()
