from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_services
from app.api.deps_auth import get_current_user_optional
from app.core.db import DatabaseUnavailableError
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.container import AppServices
from app.services.conversation_state import ConversationAccessDenied

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    services: AppServices = Depends(get_services),
    current_user: User | None = Depends(get_current_user_optional),
) -> ChatResponse:
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
    if request.conversation_id is not None:
        try:
            UUID(request.conversation_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid conversation_id.",
            ) from exc

    user_id = current_user.id if current_user else None
    payload = request.model_copy(update={"message": message})

    try:
        return services.chat_pipeline.handle_chat(payload, current_user_id=user_id)
    except ConversationAccessDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found.",
        ) from exc
    except DatabaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database is unavailable: {exc}",
        ) from exc
