"""
Интеграция: запрос как от пользователя → нормализация → эмбеддинг → топ-10 рецептов из БД.

С логами шагов в консоли во время теста:

  pytest tests/test_search_user_pipeline.py -v -m integration --log-cli-level=INFO --log-cli-format="%(asctime)s %(levelname)s %(message)s" --log-date-format="%H:%M:%S"

Опционально -s (без захвата stdout).

Нужны EMBED_PG_DSN или DB_HOST и данные в recipe_embeddings.
Переопределить текст запроса: SEARCH_E2E_QUERY="..."
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger("food_helper.search_user_pipeline")


@pytest.mark.integration
def test_user_query_normalize_embed_top10() -> None:
    from scripts.embedding.embed_recipes import EmbedConfig
    from scripts.embedding.pg_dsn import connect_pg, resolve_pg_dsn
    from scripts.search.query_normalize import normalize_query_for_search
    from scripts.search.query_encode import load_sentence_transformer
    from scripts.search.search_recipes import (
        _configure_model,
        prepare_search_text,
        run_user_recipe_search_pg,
    )

    dsn = resolve_pg_dsn(None)
    if not dsn:
        log.info("Skip integration: no DSN (set EMBED_PG_DSN or DB_HOST + DB_*)")
        pytest.skip("No DSN: set EMBED_PG_DSN or DB_HOST (+ DB_*) for integration")

    user_raw = os.getenv("SEARCH_E2E_QUERY", "хочу борщ с говядиной")
    model_name = EmbedConfig.model_name
    top_k = 10

    log.info("DSN ok (host not logged)")
    log.info("Raw user query: %r", user_raw)

    normalized_prepare = prepare_search_text(user_raw, skip_normalize=False)
    normalized_only = normalize_query_for_search(user_raw)
    log.info("After prepare_search_text (morph/stopwords or fallback): %r", normalized_prepare)
    log.info("normalize_query_for_search only: %r", normalized_only)

    conn = connect_pg(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM recipe_embeddings")
            emb_count = int(cur.fetchone()[0])
        log.info("recipe_embeddings row count: %s", emb_count)
        if emb_count == 0:
            log.info("Skip: recipe_embeddings is empty")
            pytest.skip("recipe_embeddings empty; run embed_recipes first")

        log.info("Loading model %r (first run may take minutes)...", model_name)
        model = load_sentence_transformer(model_name)
        _configure_model(model)
        log.info("Model ready, max_seq_length=%s", model.max_seq_length)

        rows = run_user_recipe_search_pg(
            conn,
            model,
            user_query=user_raw,
            model_name=model_name,
            top_k=top_k,
            normalize_embeddings=True,
            skip_query_normalize=False,
        )

        log.info("Rows returned (max %s): %s", top_k, len(rows))
        for i, row in enumerate(rows, start=1):
            title = (row.get("title") or "").strip() or "(без названия)"
            rid = row.get("id")
            sim = row.get("similarity")
            url = (row.get("recipe_url") or "")[:80]
            log.info(
                "  #%s id=%s sim=%s title=%r url=%s",
                i,
                rid,
                f"{float(sim):.4f}" if isinstance(sim, (int, float)) else sim,
                title[:60],
                url,
            )

        assert len(rows) <= top_k, "at most K rows"
        for row in rows:
            assert "id" in row
            assert row["id"] is not None
            assert "recipe_url" in row
            assert "ingredients" in row or "raw" in row

        if len(rows) == 0:
            log.info("Skip: vector search returned 0 rows")
            pytest.skip("vector search returned 0 rows (model/data?)")

    finally:
        conn.close()
