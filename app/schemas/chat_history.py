from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatListItem(BaseModel):
    conversation_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ChatListResponse(BaseModel):
    items: list[ChatListItem]


class ChatMessageItem(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class ChatDetailResponse(BaseModel):
    conversation_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageItem]


class ChatRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class ChatRenameResponse(BaseModel):
    conversation_id: UUID
    title: str
    updated_at: datetime


class ChatDeleteResponse(BaseModel):
    ok: bool = True
