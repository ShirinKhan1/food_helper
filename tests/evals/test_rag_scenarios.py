from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.orchestrator.intent_router import IntentRouter
from app.orchestrator.pipeline import ChatPipeline
from app.schemas.chat import ChatRequest
from app.services.answer_generator import AnswerGenerator
from app.services.conversation_state import ConversationSnapshot
from app.services.llm.null import NullLLMClient
from app.services.ingredient_catalog import IngredientCatalog
from app.services.recipe_repository import RecipeRepository
from app.services.substitution import SubstitutionService
from scripts.search.query_normalize import normalize_query_for_search


class DummyDatabase:
    def __init__(self, dsn: str | None) -> None:
        self.dsn = dsn


class InMemoryConversationStateService:
    def __init__(self) -> None:
        self.snapshots: dict[str, ConversationSnapshot] = {}
        self.messages: list[tuple[str, str, str]] = []

    def ensure_conversation(self, conversation_id: str | None) -> str:
        cid = conversation_id or "conv-eval"
        self.snapshots.setdefault(cid, ConversationSnapshot(conversation_id=cid))
        return cid

    def append_message(self, conversation_id: str, *, role: str, content: str) -> None:
        self.messages.append((conversation_id, role, content))

    def get_snapshot(self, conversation_id: str) -> ConversationSnapshot:
        return self.snapshots.setdefault(
            conversation_id,
            ConversationSnapshot(conversation_id=conversation_id),
        )

    def update_snapshot(
        self,
        conversation_id: str,
        *,
        last_recipe_results: list[int] | None = None,
        selected_recipe_id="__unset__",
    ) -> None:
        snapshot = self.get_snapshot(conversation_id)
        if last_recipe_results is not None:
            snapshot.last_recipe_results = last_recipe_results
        if selected_recipe_id != "__unset__":
            snapshot.selected_recipe_id = selected_recipe_id

    def resolve_reference(self, conversation_id: str, reference: dict | None) -> int | None:
        snapshot = self.get_snapshot(conversation_id)
        if not reference:
            return snapshot.selected_recipe_id
        if reference["type"] == "rank":
            rank = int(reference["value"])
            if 1 <= rank <= len(snapshot.last_recipe_results):
                return snapshot.last_recipe_results[rank - 1]
            return None
        return snapshot.selected_recipe_id


DATASET = {
    1: {
        "id": 1,
        "title": "Борщ с говядиной",
        "description": "Классический борщ",
        "calories_kcal": 210.0,
        "protein_g": 9.0,
        "fat_g": 10.0,
        "carbs_g": 12.0,
        "servings": 4,
        "recipe_url": "https://example.com/borsh-beef",
        "properties": {"Время на кухне": "60 минут", "Сложность": "3 из 5"},
        "ingredients": [{"name": "Говядина"}],
        "steps": [{"position": 1, "text": "Сварите бульон"}],
    },
    2: {
        "id": 2,
        "title": "Постный борщ",
        "description": "Борщ без мяса",
        "calories_kcal": 90.0,
        "protein_g": 3.0,
        "fat_g": 2.0,
        "carbs_g": 11.0,
        "servings": 4,
        "recipe_url": "https://example.com/lean-borsh",
        "properties": {"Время на кухне": "40 минут", "Сложность": "2 из 5"},
        "ingredients": [{"name": "Свекла"}, {"name": "Капуста"}],
        "steps": [{"position": 1, "text": "Потушите овощи"}],
    },
    3: {
        "id": 3,
        "title": "Яблочный пирог",
        "description": "Сладкая выпечка",
        "calories_kcal": 250.0,
        "protein_g": 4.0,
        "fat_g": 7.0,
        "carbs_g": 39.0,
        "servings": 6,
        "recipe_url": "https://example.com/apple-pie",
        "properties": {"Время на кухне": "50 минут", "Сложность": "2 из 5"},
        "ingredients": [{"name": "Сахар"}, {"name": "Яблоко"}],
        "steps": [{"position": 1, "text": "Смешайте тесто"}],
    },
    4: {
        "id": 4,
        "title": "Овсянка с бананом",
        "description": "Легкий завтрак",
        "calories_kcal": 140.0,
        "protein_g": 5.0,
        "fat_g": 3.0,
        "carbs_g": 21.0,
        "servings": 1,
        "recipe_url": "https://example.com/oatmeal",
        "properties": {"Время на кухне": "10 минут", "Сложность": "1 из 5"},
        "ingredients": [{"name": "Овсянка"}, {"name": "Банан"}],
        "steps": [{"position": 1, "text": "Сварите овсянку"}],
    },
    5: {
        "id": 5,
        "title": "Омлет на воде",
        "description": "Быстрый завтрак без молока",
        "calories_kcal": 120.0,
        "protein_g": 12.0,
        "fat_g": 7.0,
        "carbs_g": 2.0,
        "servings": 1,
        "recipe_url": "https://example.com/omelet",
        "properties": {"Время на кухне": "8 минут", "Сложность": "1 из 5"},
        "ingredients": [{"name": "Яйцо"}, {"name": "Вода"}],
        "steps": [{"position": 1, "text": "Взбейте яйца"}],
    },
    6: {
        "id": 6,
        "title": "Куриный салат",
        "description": "Белковый салат",
        "calories_kcal": 160.0,
        "protein_g": 18.0,
        "fat_g": 8.0,
        "carbs_g": 4.0,
        "servings": 2,
        "recipe_url": "https://example.com/chicken-salad",
        "properties": {"Время на кухне": "20 минут", "Сложность": "1 из 5"},
        "ingredients": [{"name": "Куриное филе"}, {"name": "Салат"}],
        "steps": [{"position": 1, "text": "Нарежьте курицу"}],
    },
    7: {
        "id": 7,
        "title": "Овощной салат",
        "description": "Похожий салат без курицы",
        "calories_kcal": 95.0,
        "protein_g": 2.0,
        "fat_g": 4.0,
        "carbs_g": 10.0,
        "servings": 2,
        "recipe_url": "https://example.com/veggie-salad",
        "properties": {"Время на кухне": "15 минут", "Сложность": "1 из 5"},
        "ingredients": [{"name": "Огурец"}, {"name": "Помидор"}],
        "steps": [{"position": 1, "text": "Нарежьте овощи"}],
    },
}


class InMemoryRecipeRepository:
    def __init__(self) -> None:
        self._converter = RecipeRepository(DummyDatabase("unused"))

    def get_recipe_row_by_id(self, recipe_id: int):
        return DATASET.get(recipe_id)

    def search_recipe_rows_by_text(self, query: str, *, limit: int = 5):
        lowered = query.lower()
        normalized_query = set(normalize_query_for_search(query).split())
        rows = [
            row
            for row in DATASET.values()
            if lowered in row["title"].lower()
            or lowered in row["description"].lower()
            or normalized_query.intersection(
                set(
                    normalize_query_for_search(
                        f"{row['title']} {row['description']}"
                    ).split()
                )
            )
        ]
        return rows[:limit]

    def row_to_recipe_card(self, row, *, rank: int):
        return self._converter.row_to_recipe_card(row, rank=rank)

    def row_to_recipe_detail(self, row):
        return self._converter.row_to_recipe_detail(row)


class InMemorySearchService:
    def __init__(self) -> None:
        self._catalog = IngredientCatalog.load()

    def search(self, message: str, *, constraints, top_k: int):
        lowered = message.lower()
        if "борщ" in lowered:
            rows = [DATASET[2], DATASET[1], DATASET[3]]
            if "мясо" in constraints.exclude_ingredients:
                rows = [DATASET[2], DATASET[3]]
            normalized_query = "борщ мясо"
        elif "завтрак" in lowered:
            rows = [DATASET[4], DATASET[5]]
            normalized_query = "завтрак легкий"
        elif "молоко" in lowered:
            rows = [DATASET[5], DATASET[7]]
            normalized_query = "молоко"
        elif "куриц" in lowered or "курин" in lowered:
            rows = [DATASET[6], DATASET[7]]
            normalized_query = "курица"
        elif "яблоч" in lowered:
            rows = [DATASET[3]]
            normalized_query = "яблочный пирог"
        else:
            rows = []
            normalized_query = lowered
        return SimpleExecution(normalized_query, rows[:top_k])

    def similar_recipes(self, *, normalized_query: str, base_rows: list[dict], constraints, top_k: int):
        rows = list(base_rows)
        exclusions = [*constraints.exclude_ingredients, *constraints.allergy_exclusions]
        if exclusions:
            filtered_rows = []
            for row in rows:
                if self._catalog.matches_any(row, exclusions):
                    continue
                filtered_rows.append(row)
            rows = filtered_rows
        return SimpleExecution(normalized_query, rows[:top_k])


class InMemoryVectorSearchService:
    def similar_by_recipe_id(self, recipe_id: int, *, top_k: int):
        if recipe_id == 6:
            return [DATASET[7], DATASET[6]]
        return []


class InMemoryNutritionService:
    def get_nutrition(self, recipe_id: int):
        row = DATASET[recipe_id]
        return InMemoryRecipeRepository().row_to_recipe_detail(row).nutrition

    def format_answer(self, title: str, nutrition, nutrient: str | None) -> str:
        if nutrient == "protein":
            return f'В рецепте "{title}" указано {nutrition.protein_g} г белка на 100 г.'
        if nutrient == "calories":
            return f'В рецепте "{title}" указано {nutrition.calories_kcal} кКал на 100 г.'
        return f'В рецепте "{title}" указаны БЖУ.'


class SimpleExecution:
    def __init__(self, normalized_query: str, rows: list[dict]) -> None:
        self.normalized_query = normalized_query
        self.vector_results = rows
        self.keyword_results = rows
        for row in rows:
            row.setdefault("similarity", 0.9)
            row.setdefault("final_score", 0.95)
            row.setdefault("matched_by", ["vector", "rules"])
        self.final_results = rows


def build_pipeline(state_service: InMemoryConversationStateService) -> ChatPipeline:
    settings = Settings.from_env()
    answer_generator = AnswerGenerator(
        llm_client=NullLLMClient(),
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        num_ctx=settings.llm_num_ctx,
        think=settings.llm_think,
    )
    return ChatPipeline(
        settings=settings,
        router=IntentRouter(),
        search_service=InMemorySearchService(),
        vector_search_service=InMemoryVectorSearchService(),
        recipe_repository=InMemoryRecipeRepository(),
        nutrition_service=InMemoryNutritionService(),
        substitution_service=SubstitutionService(IngredientCatalog.load()),
        conversation_state_service=state_service,
        answer_generator=answer_generator,
    )


def test_scenario_1_search_without_meat() -> None:
    state = InMemoryConversationStateService()
    pipeline = build_pipeline(state)
    response = pipeline.handle_chat(ChatRequest(conversation_id="c1", message="Какие есть рецепты с борщом без мяса?"))
    assert response.intent == "search_recipes"
    assert response.route == "hybrid_search"
    assert all("говядин" not in recipe.title.lower() for recipe in response.recipes)


def test_scenario_2_substitution_by_rank() -> None:
    state = InMemoryConversationStateService()
    state.snapshots["c2"] = ConversationSnapshot(conversation_id="c2", last_recipe_results=[1, 2, 3])
    pipeline = build_pipeline(state)
    response = pipeline.handle_chat(
        ChatRequest(conversation_id="c2", message="На что в третьем рецепте можно заменить сахар?")
    )
    assert response.intent == "ingredient_substitution"
    assert response.substitutions


def test_scenario_3_light_breakfast() -> None:
    state = InMemoryConversationStateService()
    pipeline = build_pipeline(state)
    response = pipeline.handle_chat(
        ChatRequest(conversation_id="c3", message="Что можно приготовить на завтрак, чтобы оно было легкое?")
    )
    assert response.intent == "recommend_recipes"
    assert response.recipes


def test_scenario_4_nutrition_by_title() -> None:
    state = InMemoryConversationStateService()
    pipeline = build_pipeline(state)
    response = pipeline.handle_chat(
        ChatRequest(conversation_id="c4", message="Сколько калорий в яблочном пироге?")
    )
    assert response.intent == "nutrition_question"
    assert response.nutrition is not None
    assert response.nutrition.calories_kcal == 250.0


def test_scenario_5_recipe_details_by_rank() -> None:
    state = InMemoryConversationStateService()
    state.snapshots["c5"] = ConversationSnapshot(conversation_id="c5", last_recipe_results=[1, 2, 3])
    pipeline = build_pipeline(state)
    response = pipeline.handle_chat(ChatRequest(conversation_id="c5", message="Покажи второй рецепт."))
    assert response.intent == "recipe_details"
    assert response.selected_recipe is not None
    assert response.selected_recipe.recipe_id == 2


def test_scenario_6_protein_by_rank() -> None:
    state = InMemoryConversationStateService()
    state.snapshots["c6"] = ConversationSnapshot(conversation_id="c6", last_recipe_results=[5, 4, 3])
    pipeline = build_pipeline(state)
    response = pipeline.handle_chat(ChatRequest(conversation_id="c6", message="Сколько белка в первом?"))
    assert response.intent == "nutrition_question"
    assert "белка" in response.answer


def test_nutrition_with_ingredient_query_returns_candidates() -> None:
    state = InMemoryConversationStateService()
    pipeline = build_pipeline(state)

    response = pipeline.handle_chat(
        ChatRequest(conversation_id="c-nutrition-search", message="Сколько калорий и белка в рецепте с курицей?")
    )

    assert response.intent == "nutrition_question"
    assert response.route == "hybrid_search"
    assert response.recipes
    assert response.nutrition is None
    assert "кКал" in response.answer
    assert "г белка" in response.answer
    assert "Выберите номер" not in response.answer
    assert state.get_snapshot("c-nutrition-search").last_recipe_results == [
        recipe.recipe_id for recipe in response.recipes
    ]


def test_flow_search_details_then_nutrition_keeps_selected_recipe() -> None:
    state = InMemoryConversationStateService()
    pipeline = build_pipeline(state)

    search_response = pipeline.handle_chat(
        ChatRequest(conversation_id="flow-1", message="Найди рецепты с борщом без мяса")
    )
    assert search_response.recipes

    details_response = pipeline.handle_chat(
        ChatRequest(conversation_id="flow-1", message="Покажи первый рецепт")
    )
    assert details_response.selected_recipe is not None
    assert state.get_snapshot("flow-1").selected_recipe_id == details_response.selected_recipe.recipe_id

    nutrition_response = pipeline.handle_chat(
        ChatRequest(conversation_id="flow-1", message="Сколько белка в нём?")
    )
    assert nutrition_response.nutrition is not None
    assert nutrition_response.selected_recipe is not None
    assert nutrition_response.selected_recipe.recipe_id == details_response.selected_recipe.recipe_id


def test_general_substitution_without_recipe_context() -> None:
    state = InMemoryConversationStateService()
    pipeline = build_pipeline(state)

    response = pipeline.handle_chat(
        ChatRequest(conversation_id="c-general", message="Чем заменить молоко?")
    )

    assert response.intent == "general_substitution"
    assert response.route == "substitution_catalog"
    assert response.substitutions
    assert response.selected_recipe is None


def test_recipe_substitution_falls_back_to_general_without_recipe() -> None:
    state = InMemoryConversationStateService()
    pipeline = build_pipeline(state)

    response = pipeline.handle_chat(
        ChatRequest(conversation_id="c-fallback", message="На что можно заменить молоко в рецепте?")
    )

    assert response.intent == "general_substitution"
    assert response.route == "substitution_catalog"
    assert response.substitutions


def test_recipe_title_ambiguity_returns_candidates() -> None:
    state = InMemoryConversationStateService()
    pipeline = build_pipeline(state)

    response = pipeline.handle_chat(
        ChatRequest(conversation_id="c-ambiguous", message="Сколько калорий в борще?")
    )

    assert response.intent == "nutrition_question"
    assert response.recipes
    assert response.selected_recipe is None
    assert state.get_snapshot("c-ambiguous").last_recipe_results == [
        recipe.recipe_id for recipe in response.recipes
    ]


def test_scenario_7_allergy_warning() -> None:
    state = InMemoryConversationStateService()
    pipeline = build_pipeline(state)
    response = pipeline.handle_chat(ChatRequest(conversation_id="c7", message="Мне нельзя молоко, что подойдет?"))
    assert response.intent == "allergy_or_exclusion"
    assert response.warnings


def test_scenario_8_similar_without_chicken() -> None:
    state = InMemoryConversationStateService()
    state.snapshots["c8"] = ConversationSnapshot(conversation_id="c8", selected_recipe_id=6)
    pipeline = build_pipeline(state)
    response = pipeline.handle_chat(
        ChatRequest(conversation_id="c8", message="Есть что-то похожее, но без курицы?")
    )
    assert response.intent == "similar_recipes"
    assert response.recipes
    assert all("кур" not in recipe.title.lower() for recipe in response.recipes)
    assert state.get_snapshot("c8").selected_recipe_id == 6
    assert all(recipe.recipe_id != 6 for recipe in response.recipes)
