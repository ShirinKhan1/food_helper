from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.db import Database
from app.orchestrator.intent_router import IntentRouter
from app.orchestrator.pipeline import ChatPipeline
from app.services.conversation_state import ConversationStateService
from app.services.embeddings import EmbeddingService
from app.services.hybrid_search import HybridSearchService
from app.services.ingredient_catalog import IngredientCatalog
from app.services.keyword_search import KeywordSearchService
from app.services.nutrition import NutritionService
from app.services.recipe_repository import RecipeRepository
from app.services.search_service import SearchService
from app.services.substitution import SubstitutionService
from app.services.vector_search import VectorSearchService


@dataclass
class AppServices:
    settings: Settings
    db: Database
    ingredient_catalog: IngredientCatalog
    embedding_service: EmbeddingService
    recipe_repository: RecipeRepository
    vector_search_service: VectorSearchService
    keyword_search_service: KeywordSearchService
    hybrid_search_service: HybridSearchService
    search_service: SearchService
    nutrition_service: NutritionService
    substitution_service: SubstitutionService
    conversation_state_service: ConversationStateService
    intent_router: IntentRouter
    chat_pipeline: ChatPipeline


def build_services(settings: Settings | None = None) -> AppServices:
    resolved_settings = settings or Settings.from_env()
    db = Database(resolved_settings.db_dsn)
    ingredient_catalog = IngredientCatalog.load()
    embedding_service = EmbeddingService(resolved_settings)
    recipe_repository = RecipeRepository(db)
    vector_search_service = VectorSearchService(db, resolved_settings)
    keyword_search_service = KeywordSearchService(recipe_repository)
    hybrid_search_service = HybridSearchService(
        vector_search=vector_search_service,
        keyword_search=keyword_search_service,
        ingredient_catalog=ingredient_catalog,
    )
    search_service = SearchService(
        embedding_service=embedding_service,
        hybrid_search_service=hybrid_search_service,
    )
    nutrition_service = NutritionService(recipe_repository)
    substitution_service = SubstitutionService(ingredient_catalog)
    conversation_state_service = ConversationStateService(db)
    intent_router = IntentRouter()
    chat_pipeline = ChatPipeline(
        settings=resolved_settings,
        router=intent_router,
        search_service=search_service,
        vector_search_service=vector_search_service,
        recipe_repository=recipe_repository,
        nutrition_service=nutrition_service,
        substitution_service=substitution_service,
        conversation_state_service=conversation_state_service,
    )
    return AppServices(
        settings=resolved_settings,
        db=db,
        ingredient_catalog=ingredient_catalog,
        embedding_service=embedding_service,
        recipe_repository=recipe_repository,
        vector_search_service=vector_search_service,
        keyword_search_service=keyword_search_service,
        hybrid_search_service=hybrid_search_service,
        search_service=search_service,
        nutrition_service=nutrition_service,
        substitution_service=substitution_service,
        conversation_state_service=conversation_state_service,
        intent_router=intent_router,
        chat_pipeline=chat_pipeline,
    )
