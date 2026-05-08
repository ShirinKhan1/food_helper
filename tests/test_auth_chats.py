from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg2.errors
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import create_access_token, decode_user_id_from_token, hash_password, verify_password
from app.main import create_app
from app.models.user import User
from app.schemas.chat import ChatResponse
from tests.test_api import FakeChatPipeline, FakeDB, FakeEmbeddingService, FakeRecipeRepository, FakeSearchService


@pytest.fixture
def settings() -> Settings:
    return replace(
        Settings.from_env(),
        auth_secret_key="unit-test-secret-key-32chars-minimum!!",
        auth_cookie_name="food_helper_access_token",
        auth_access_token_expire_minutes=60,
        auth_cookie_secure=False,
        frontend_origin="http://localhost:3000",
    )


def test_password_hash_and_jwt_roundtrip(settings: Settings) -> None:
    h = hash_password("password123")
    assert verify_password("password123", h)
    assert not verify_password("wrong", h)
    uid = str(uuid4())
    tok = create_access_token(uid, settings)
    assert decode_user_id_from_token(tok, settings) == uid
    assert decode_user_id_from_token("bad", settings) is None


class MemUserRepository:
    def __init__(self) -> None:
        self._by_email: dict[str, User] = {}
        self._hash: dict[UUID, str] = {}

    def create_user(self, email: str, password_hash: str) -> User:
        norm = email.strip().lower()
        if norm in self._by_email:
            raise psycopg2.errors.UniqueViolation()
        user = User(id=uuid4(), email=norm, created_at=datetime.now(timezone.utc))
        self._by_email[norm] = user
        self._hash[user.id] = password_hash
        return user

    def get_by_id(self, user_id: UUID) -> User | None:
        for u in self._by_email.values():
            if u.id == user_id:
                return u
        return None

    def get_password_hash_by_email(self, email: str) -> tuple[UUID, str] | None:
        norm = email.strip().lower()
        u = self._by_email.get(norm)
        if u is None:
            return None
        return u.id, self._hash[u.id]


class MemChatHistoryRepository:
    def __init__(self) -> None:
        self.sessions: dict[UUID, dict] = {}

    def list_chats(self, user_id: UUID) -> list[dict]:
        rows = [v for v in self.sessions.values() if v["user_id"] == user_id]
        rows.sort(key=lambda r: r["updated_at"], reverse=True)
        return [
            {
                "conversation_id": r["conversation_id"],
                "title": r.get("title"),
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    def get_chat_with_messages(self, user_id: UUID, conversation_id: UUID) -> dict | None:
        s = self.sessions.get(conversation_id)
        if s is None or s["user_id"] != user_id:
            return None
        return {"session": s["session"], "messages": list(s["messages"])}

    def update_title(self, user_id: UUID, conversation_id: UUID, title: str) -> dict | None:
        s = self.sessions.get(conversation_id)
        if s is None or s["user_id"] != user_id:
            return None
        s["session"]["title"] = title
        s["updated_at"] = datetime.now(timezone.utc)
        return {
            "conversation_id": conversation_id,
            "title": title,
            "updated_at": s["updated_at"],
        }

    def delete_chat(self, user_id: UUID, conversation_id: UUID) -> bool:
        s = self.sessions.get(conversation_id)
        if s is None or s["user_id"] != user_id:
            return False
        del self.sessions[conversation_id]
        return True

    def seed_chat(self, user_id: UUID, conversation_id: UUID) -> None:
        now = datetime.now(timezone.utc)
        self.sessions[conversation_id] = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "created_at": now,
            "updated_at": now,
            "title": "Test chat",
            "session": {
                "conversation_id": conversation_id,
                "title": "Test chat",
                "created_at": now,
                "updated_at": now,
            },
            "messages": [
                {"id": 1, "role": "user", "content": "hi", "created_at": now},
                {"id": 2, "role": "assistant", "content": "hello", "created_at": now},
            ],
        }


def _full_services(settings: Settings, users: MemUserRepository, chats: MemChatHistoryRepository):
    response = ChatResponse(
        conversation_id=str(uuid4()),
        answer="ok",
        intent="search_recipes",
        route="hybrid_search",
        recipes=[],
        warnings=[],
        sources=[],
    )
    return SimpleNamespace(
        settings=settings,
        db=FakeDB(),
        embedding_service=FakeEmbeddingService(),
        ingredient_catalog=SimpleNamespace(),
        recipe_repository=FakeRecipeRepository(),
        vector_search_service=SimpleNamespace(),
        keyword_search_service=SimpleNamespace(),
        hybrid_search_service=SimpleNamespace(),
        search_service=FakeSearchService(),
        nutrition_service=SimpleNamespace(),
        substitution_service=SimpleNamespace(),
        conversation_state_service=SimpleNamespace(),
        intent_router=SimpleNamespace(),
        answer_generator=SimpleNamespace(),
        chat_pipeline=FakeChatPipeline(response=response),
        user_repository=users,
        chat_history_repository=chats,
    )


def test_register_login_me_logout(settings: Settings) -> None:
    users = MemUserRepository()
    chats = MemChatHistoryRepository()
    client = TestClient(create_app(settings=settings, services=_full_services(settings, users, chats)))

    r = client.post("/v1/auth/register", json={"email": "A@Example.com", "password": "password123"})
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "a@example.com"
    assert client.cookies.get("food_helper_access_token")

    r2 = client.get("/v1/auth/me")
    assert r2.status_code == 200
    assert r2.json()["user"]["email"] == "a@example.com"

    client.post("/v1/auth/logout")
    r3 = client.get("/v1/auth/me")
    assert r3.json()["user"] is None


def test_register_duplicate_email(settings: Settings) -> None:
    users = MemUserRepository()
    chats = MemChatHistoryRepository()
    client = TestClient(create_app(settings=settings, services=_full_services(settings, users, chats)))
    assert (
        client.post("/v1/auth/register", json={"email": "u@example.com", "password": "password123"}).status_code
        == 200
    )
    r = client.post("/v1/auth/register", json={"email": "U@example.com", "password": "password12345"})
    assert r.status_code == 409


def test_login_wrong_password(settings: Settings) -> None:
    users = MemUserRepository()
    chats = MemChatHistoryRepository()
    users.create_user("x@example.com", hash_password("rightpass"))
    client = TestClient(create_app(settings=settings, services=_full_services(settings, users, chats)))
    r = client.post("/v1/auth/login", json={"email": "x@example.com", "password": "wrongpass"})
    assert r.status_code == 401


def test_chats_require_auth(settings: Settings) -> None:
    users = MemUserRepository()
    chats = MemChatHistoryRepository()
    client = TestClient(create_app(settings=settings, services=_full_services(settings, users, chats)))
    assert client.get("/v1/chats").status_code == 401


def test_chats_isolation(settings: Settings) -> None:
    users = MemUserRepository()
    chats = MemChatHistoryRepository()
    u1 = users.create_user("a@example.com", hash_password("password123"))
    u2 = users.create_user("b@example.com", hash_password("password123"))
    cid = uuid4()
    chats.seed_chat(u1.id, cid)

    client_b = TestClient(create_app(settings=settings, services=_full_services(settings, users, chats)))
    token_b = create_access_token(str(u2.id), settings)
    client_b.cookies.set("food_helper_access_token", token_b)

    assert client_b.get(f"/v1/chats/{cid}").status_code == 404
    assert client_b.patch(f"/v1/chats/{cid}", json={"title": "x"}).status_code == 404
    assert client_b.delete(f"/v1/chats/{cid}").status_code == 404

    client_a = TestClient(create_app(settings=settings, services=_full_services(settings, users, chats)))
    token_a = create_access_token(str(u1.id), settings)
    client_a.cookies.set("food_helper_access_token", token_a)
    assert client_a.get(f"/v1/chats/{cid}").status_code == 200
