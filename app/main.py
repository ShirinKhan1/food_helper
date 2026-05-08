from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_auth import router as auth_router
from app.api.routes_chat import router as chat_router
from app.api.routes_chats import router as chats_router
from app.api.routes_debug import router as debug_router
from app.api.routes_recipes import router as recipes_router
from app.core.config import Settings
from app.core.db import DatabaseUnavailableError
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
    def health() -> dict[str, str]:
        try:
            db_status = resolved_services.db.ping()
        except DatabaseUnavailableError:
            db_status = "error"

        return {
            "status": "ok" if db_status == "ok" else "degraded",
            "db": db_status,
            "embedding_model": resolved_services.embedding_service.health_status(),
        }

    return app


app = create_app()
