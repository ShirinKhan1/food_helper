from __future__ import annotations

import psycopg2.errors
from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_services
from app.api.deps_auth import get_current_user_optional
from app.core.db import DatabaseUnavailableError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import AuthUserResponse, LoginRequest, LogoutResponse, MeResponse, RegisterRequest, UserPublic
from app.services.container import AppServices

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _set_auth_cookie(response: Response, services: AppServices, user_id: str) -> None:
    token = create_access_token(user_id, services.settings)
    max_age = services.settings.auth_access_token_expire_minutes * 60
    response.set_cookie(
        key=services.settings.auth_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=services.settings.auth_cookie_secure,
        max_age=max_age,
        path="/",
    )


def _clear_auth_cookie(response: Response, services: AppServices) -> None:
    response.delete_cookie(
        key=services.settings.auth_cookie_name,
        path="/",
        samesite="lax",
        secure=services.settings.auth_cookie_secure,
    )


def _user_public(user: User) -> UserPublic:
    return UserPublic(id=user.id, email=user.email, created_at=user.created_at)


@router.post("/register", response_model=AuthUserResponse)
def register(
    body: RegisterRequest,
    response: Response,
    services: AppServices = Depends(get_services),
) -> AuthUserResponse:
    try:
        hashed = hash_password(body.password)
        user = services.user_repository.create_user(str(body.email), hashed)
    except DatabaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except psycopg2.errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered.",
        ) from exc

    _set_auth_cookie(response, services, str(user.id))
    return AuthUserResponse(user=_user_public(user))


@router.post("/login", response_model=AuthUserResponse)
def login(
    body: LoginRequest,
    response: Response,
    services: AppServices = Depends(get_services),
) -> AuthUserResponse:
    try:
        row = services.user_repository.get_password_hash_by_email(str(body.email))
    except DatabaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    user_id, password_hash = row
    if not verify_password(body.password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    user = services.user_repository.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    _set_auth_cookie(response, services, str(user.id))
    return AuthUserResponse(user=_user_public(user))


@router.post("/logout", response_model=LogoutResponse)
def logout(response: Response, services: AppServices = Depends(get_services)) -> LogoutResponse:
    _clear_auth_cookie(response, services)
    return LogoutResponse(ok=True)


@router.get("/me", response_model=MeResponse)
def me(user: User | None = Depends(get_current_user_optional)) -> MeResponse:
    if user is None:
        return MeResponse(user=None)
    return MeResponse(user=_user_public(user))
