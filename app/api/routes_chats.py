from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_services
from app.api.deps_auth import get_current_user
from app.core.db import DatabaseUnavailableError
from app.models.user import User
from app.schemas.chat_history import (
    ChatDeleteResponse,
    ChatDetailResponse,
    ChatListItem,
    ChatListResponse,
    ChatMessageItem,
    ChatRenameRequest,
    ChatRenameResponse,
)
from app.services.container import AppServices

router = APIRouter(prefix="/v1/chats", tags=["chats"])


@router.get("", response_model=ChatListResponse)
def list_chats(
    user: User = Depends(get_current_user),
    services: AppServices = Depends(get_services),
) -> ChatListResponse:
    try:
        rows = services.chat_history_repository.list_chats(user.id)
    except DatabaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    items = [
        ChatListItem(
            conversation_id=r["conversation_id"],
            title=r.get("title"),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]
    return ChatListResponse(items=items)


@router.get("/{conversation_id}", response_model=ChatDetailResponse)
def get_chat(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    services: AppServices = Depends(get_services),
) -> ChatDetailResponse:
    try:
        data = services.chat_history_repository.get_chat_with_messages(user.id, conversation_id)
    except DatabaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found.")
    s = data["session"]
    messages = [
        ChatMessageItem(
            id=m["id"],
            role=m["role"],
            content=m["content"],
            created_at=m["created_at"],
        )
        for m in data["messages"]
    ]
    return ChatDetailResponse(
        conversation_id=s["conversation_id"],
        title=s.get("title"),
        created_at=s["created_at"],
        updated_at=s["updated_at"],
        messages=messages,
    )


@router.patch("/{conversation_id}", response_model=ChatRenameResponse)
def rename_chat(
    conversation_id: UUID,
    body: ChatRenameRequest,
    user: User = Depends(get_current_user),
    services: AppServices = Depends(get_services),
) -> ChatRenameResponse:
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Title must not be empty.")
    try:
        row = services.chat_history_repository.update_title(user.id, conversation_id, title)
    except DatabaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found.")
    return ChatRenameResponse(
        conversation_id=row["conversation_id"],
        title=row["title"],
        updated_at=row["updated_at"],
    )


@router.delete("/{conversation_id}", response_model=ChatDeleteResponse)
def delete_chat(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    services: AppServices = Depends(get_services),
) -> ChatDeleteResponse:
    try:
        deleted = services.chat_history_repository.delete_chat(user.id, conversation_id)
    except DatabaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found.")
    return ChatDeleteResponse(ok=True)
