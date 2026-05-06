from __future__ import annotations

from app.schemas.search import QueryConstraints
from app.services.embeddings import EmbeddingService
from app.services.hybrid_search import HybridSearchExecution, HybridSearchService
from scripts.search.search_recipes import prepare_search_text


class SearchService:
    def __init__(
        self,
        *,
        embedding_service: EmbeddingService,
        hybrid_search_service: HybridSearchService,
    ) -> None:
        self._embedding_service = embedding_service
        self._hybrid_search_service = hybrid_search_service

    def search(self, message: str, *, constraints: QueryConstraints, top_k: int) -> HybridSearchExecution:
        normalized_query = prepare_search_text(message, skip_normalize=False)
        query_embedding = self._embedding_service.encode_query(normalized_query)
        return self._hybrid_search_service.run(
            normalized_query=normalized_query,
            query_embedding=query_embedding,
            constraints=constraints,
            top_k=top_k,
        )

    def similar_recipes(
        self,
        *,
        normalized_query: str,
        base_rows: list[dict],
        constraints: QueryConstraints,
        top_k: int,
    ) -> HybridSearchExecution:
        return self._hybrid_search_service.filter_similar(
            base_rows,
            normalized_query=normalized_query,
            constraints=constraints,
            top_k=top_k,
        )
