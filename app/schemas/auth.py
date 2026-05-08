from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: UUID
    email: str
    created_at: datetime


class AuthUserResponse(BaseModel):
    user: UserPublic


class MeResponse(BaseModel):
    user: UserPublic | None


class LogoutResponse(BaseModel):
    ok: bool = True
