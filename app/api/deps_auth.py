from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Request, status

from app.api.deps import get_services
from app.core.security import decode_user_id_from_token
from app.models.user import User
from app.services.container import AppServices


def get_current_user_optional(
    request: Request,
    services: AppServices = Depends(get_services),
) -> User | None:
    token = request.cookies.get(services.settings.auth_cookie_name)
    if not token:
        return None
    uid_str = decode_user_id_from_token(token, services.settings)
    if not uid_str:
        return None
    try:
        uid = UUID(uid_str)
    except ValueError:
        return None
    return services.user_repository.get_by_id(uid)


def get_current_user(user: User | None = Depends(get_current_user_optional)) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    return user
