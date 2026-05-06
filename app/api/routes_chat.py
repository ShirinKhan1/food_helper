from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_services
from app.core.db import DatabaseUnavailableError
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.container import AppServices

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, services: AppServices = Depends(get_services)) -> ChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message must not be empty.",
        )
    if len(message) > services.settings.max_message_chars:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Message is too long. Max length is {services.settings.max_message_chars} characters.",
        )

    try:
        return services.chat_pipeline.handle_chat(request)
    except DatabaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database is unavailable: {exc}",
        ) from exc
