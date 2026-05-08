from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from uuid import UUID

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.db import DatabaseUnavailableError
from app.main import create_app
from app.schemas.chat import ChatDebugInfo, ChatRequest, ChatResponse
from app.schemas.recipe import NutritionInfo, RecipeDetail
from app.schemas.search import QueryConstraints


class FakeDB:
    def ping(self) -> str:
        return "ok"


class FakeEmbeddingService:
    def maybe_preload(self) -> None:
        return None

    def health_status(self) -> str:
        return "loaded"


class FakeChatPipeline:
    def __init__(self, response: ChatResponse | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error

    def handle_chat(self, request: ChatRequest, current_user_id: UUID | None = None) -> ChatResponse:
        if self._error:
            raise self._error
        assert request.message
        assert self._response is not None
        return self._response


class FakeSearchService:
    def search(self, message: str, *, constraints: QueryConstraints, top_k: int):
        return SimpleNamespace(
            normalized_query="борщ мясо",
            vector_results=[
                {
                    "id": 1,
                    "title": "Борщ",
                    "recipe_url": "https://example.com/borsh",
                    "similarity": 0.9,
                }
            ],
            keyword_results=[],
            final_results=[
                {
                    "id": 1,
                    "title": "Борщ",
                    "recipe_url": "https://example.com/borsh",
                    "similarity": 0.9,
                    "final_score": 0.95,
                    "matched_by": ["vector", "rules"],
                }
            ],
        )


class FakeRecipeRepository:
    def get_recipe_row_by_id(self, recipe_id: int):
        if recipe_id != 7:
            return None
        return {
            "id": 7,
            "title": "Омлет",
            "description": "Быстрый завтрак",
            "calories_kcal": 146.0,
            "protein_g": 11.0,
            "fat_g": 3.8,
            "carbs_g": 16.6,
            "servings": 2,
            "recipe_url": "https://example.com/omelet",
            "properties": {"Время на кухне": "10 минут", "Сложность": "1 из 5"},
            "ingredients": [{"name": "Яйцо", "quantity": "2 шт"}],
            "steps": [{"position": 1, "text": "Взбейте яйца"}],
        }

    def row_to_recipe_detail(self, row):
        return RecipeDetail(
            recipe_id=row["id"],
            title=row["title"],
            description=row["description"],
            ingredients=[],
            steps=[],
            nutrition=NutritionInfo(
                calories_kcal=row["calories_kcal"],
                protein_g=row["protein_g"],
                fat_g=row["fat_g"],
                carbs_g=row["carbs_g"],
                serving_size="100 г",
            ),
            properties={},
            servings=row["servings"],
            recipe_url=row["recipe_url"],
        )


def _services(chat_pipeline: FakeChatPipeline | None = None):
    response = ChatResponse(
        conversation_id="conv-1",
        answer="API работает, intent распознан",
        intent="search_recipes",
        route="hybrid_search",
        recipes=[],
        warnings=[],
        sources=[],
    )
    settings = SimpleNamespace(
        max_message_chars=1000,
        auth_cookie_name="food_helper_access_token",
        auth_secret_key="unit-test-secret-key-32chars-minimum",
        auth_access_token_expire_minutes=10080,
        auth_cookie_secure=False,
        frontend_origin="http://localhost:3000",
    )
    user_repository = SimpleNamespace(
        get_by_id=lambda _id: None,
        create_user=lambda *a, **k: (_ for _ in ()).throw(NotImplementedError()),
        get_password_hash_by_email=lambda _e: None,
    )
    chat_history_repository = SimpleNamespace(
        list_chats=lambda _uid: [],
        get_chat_with_messages=lambda *_a: None,
        update_title=lambda *_a: None,
        delete_chat=lambda *_a: False,
    )
    return SimpleNamespace(
        settings=settings,
        db=FakeDB(),
        embedding_service=FakeEmbeddingService(),
        chat_pipeline=chat_pipeline or FakeChatPipeline(response=response),
        search_service=FakeSearchService(),
        recipe_repository=FakeRecipeRepository(),
        user_repository=user_repository,
        chat_history_repository=chat_history_repository,
    )


def test_chat_endpoint_rejects_invalid_conversation_id() -> None:
    client = TestClient(create_app(services=_services()))
    r = client.post(
        "/v1/chat",
        json={"message": "hello", "conversation_id": "not-a-uuid"},
    )
    assert r.status_code == 400


def test_health_endpoint() -> None:
    client = TestClient(create_app(services=_services()))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["db"] == "ok"


def test_chat_endpoint_rejects_empty_message() -> None:
    client = TestClient(create_app(services=_services()))
    response = client.post("/v1/chat", json={"message": "   "})
    assert response.status_code == 400


def test_chat_endpoint_handles_db_error() -> None:
    client = TestClient(
        create_app(
            services=_services(
                chat_pipeline=FakeChatPipeline(error=DatabaseUnavailableError("db down"))
            )
        )
    )
    response = client.post("/v1/chat", json={"message": "борщ"})
    assert response.status_code == 503
    assert "Database is unavailable" in response.json()["detail"]


def test_chat_endpoint_include_debug_contains_llm_block() -> None:
    response_payload = ChatResponse(
        conversation_id="conv-debug",
        answer="ok",
        intent="search_recipes",
        route="hybrid_search",
        recipes=[],
        warnings=[],
        sources=[],
        debug=ChatDebugInfo(llm={"used_llm": False, "fallback_reason": "answer_mode_template"}),
    )
    client = TestClient(create_app(services=_services(chat_pipeline=FakeChatPipeline(response=response_payload))))
    response = client.post("/v1/chat", json={"message": "борщ", "options": {"include_debug": True}})
    assert response.status_code == 200
    data = response.json()
    assert data["debug"]["llm"]["used_llm"] is False


def test_search_debug_endpoint() -> None:
    client = TestClient(create_app(services=_services()))
    response = client.post("/v1/search/debug", json={"query": "борщ без мяса", "top_k": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["normalized_query"] == "борщ мясо"
    assert data["constraints"]["exclude_ingredients"] == ["мясо"]
    assert len(data["final_results"]) == 1


def test_get_recipe_endpoint() -> None:
    client = TestClient(create_app(services=_services()))
    response = client.get("/v1/recipes/7")
    assert response.status_code == 200
    assert response.json()["recipe_id"] == 7
