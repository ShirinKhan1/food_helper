from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.db import Database
from app.orchestrator.intent_router import IntentRouter
from app.orchestrator.clarification import ClarificationManager
from app.orchestrator.parsed_request_adapter import ParsedRequestAdapter
from app.orchestrator.pipeline import ChatPipeline
from app.services.llm.parser_postcheck import ParserPostcheck
from app.services.llm.query_parser import LLMQueryParser
from app.services.answer_generator import AnswerGenerator
from app.services.chat_history_repository import ChatHistoryRepository
from app.services.conversation_state import ConversationStateService
from app.services.embeddings import EmbeddingService
from app.services.hybrid_search import HybridSearchService
from app.services.ingredient_catalog import IngredientCatalog
from app.services.keyword_search import KeywordSearchService
from app.services.nutrition import NutritionService
from app.services.recipe_repository import RecipeRepository
from app.services.llm.null import NullLLMClient
from app.services.llm.ollama import OllamaLLMClient
from app.services.search_service import SearchService
from app.services.substitution import SubstitutionService
from app.services.user_repository import UserRepository
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
    answer_generator: AnswerGenerator
    chat_pipeline: ChatPipeline
    user_repository: UserRepository
    chat_history_repository: ChatHistoryRepository


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
    user_repository = UserRepository(db)
    chat_history_repository = ChatHistoryRepository(db)
    intent_router = IntentRouter()
    parser_postcheck = ParserPostcheck(
        max_question_chars=resolved_settings.clarification_max_question_chars,
    )
    if resolved_settings.llm_query_parser_enabled and resolved_settings.llm_query_parser_provider == "ollama":
        parser_llm_client = OllamaLLMClient(
            base_url=resolved_settings.llm_base_url,
            model=resolved_settings.llm_query_parser_model,
            timeout_seconds=resolved_settings.llm_query_parser_timeout_seconds,
        )
    else:
        parser_llm_client = None
    query_parser = LLMQueryParser(
        settings=resolved_settings,
        llm_client=parser_llm_client,
        postcheck=parser_postcheck,
    )
    parsed_request_adapter = ParsedRequestAdapter(settings=resolved_settings)
    clarification_manager = ClarificationManager()
    if resolved_settings.llm_enabled and resolved_settings.llm_provider == "ollama":
        llm_client = OllamaLLMClient(
            base_url=resolved_settings.llm_base_url,
            model=resolved_settings.llm_model,
            timeout_seconds=resolved_settings.llm_timeout_seconds,
        )
    else:
        llm_client = NullLLMClient()

    answer_generator = AnswerGenerator(
        llm_client=llm_client,
        temperature=resolved_settings.llm_temperature,
        max_tokens=resolved_settings.llm_max_tokens,
        num_ctx=resolved_settings.llm_num_ctx,
        think=resolved_settings.llm_think,
        llm_enabled=resolved_settings.llm_enabled,
        answer_mode=resolved_settings.answer_mode,
        llm_postcheck_enabled=resolved_settings.llm_postcheck_enabled,
        llm_strict_context=resolved_settings.llm_strict_context,
        llm_max_answer_chars=resolved_settings.llm_max_answer_chars,
        llm_strip_think_tags=resolved_settings.llm_strip_think_tags,
        llm_log_prompts=resolved_settings.llm_log_prompts,
        llm_log_responses=resolved_settings.llm_log_responses,
        llm_min_recipes_for_list_answer=resolved_settings.llm_min_recipes_for_list_answer,
        llm_max_context_recipes=resolved_settings.llm_max_context_recipes,
        llm_max_context_ingredients=resolved_settings.llm_max_context_ingredients,
        llm_max_context_steps=resolved_settings.llm_max_context_steps,
    )
    chat_pipeline = ChatPipeline(
        settings=resolved_settings,
        router=intent_router,
        search_service=search_service,
        vector_search_service=vector_search_service,
        recipe_repository=recipe_repository,
        nutrition_service=nutrition_service,
        substitution_service=substitution_service,
        conversation_state_service=conversation_state_service,
        answer_generator=answer_generator,
        query_parser=query_parser,
        parsed_request_adapter=parsed_request_adapter,
        clarification_manager=clarification_manager,
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
        answer_generator=answer_generator,
        chat_pipeline=chat_pipeline,
        user_repository=user_repository,
        chat_history_repository=chat_history_repository,
    )
