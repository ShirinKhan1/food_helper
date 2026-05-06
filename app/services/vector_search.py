from __future__ import annotations

from typing import Any

from psycopg2.extras import RealDictCursor

from app.core.config import Settings
from app.core.db import Database
from scripts.search.pg_vector_search import register_pgvector, search_topk_enriched


class VectorSearchService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    def search(self, query_embedding: list[float], *, top_k: int) -> list[dict[str, Any]]:
        with self._db.connection() as conn:
            return search_topk_enriched(
                conn,
                query_embedding,
                model_name=self._settings.embedding_model_name,
                k=top_k,
            )

    def similar_by_recipe_id(self, recipe_id: int, *, top_k: int) -> list[dict[str, Any]]:
        with self._db.connection() as conn:
            register_pgvector(conn)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT embedding
                    FROM recipe_embeddings
                    WHERE recipe_id = %s AND model = %s
                    """,
                    (recipe_id, self._settings.embedding_model_name),
                )
                row = cur.fetchone()
            if not row:
                return []
            base_embedding = row["embedding"]
            rows = search_topk_enriched(
                conn,
                list(base_embedding),
                model_name=self._settings.embedding_model_name,
                k=top_k + 1,
            )
        return [row for row in rows if int(row["id"]) != recipe_id][:top_k]
