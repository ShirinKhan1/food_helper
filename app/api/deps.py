from __future__ import annotations

from fastapi import Request

from app.services.container import AppServices


def get_services(request: Request) -> AppServices:
    return request.app.state.services
