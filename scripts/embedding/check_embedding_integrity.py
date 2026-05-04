"""
Проверка согласованности recipes и recipe_embeddings (Postgres + pgvector).

Пример:
  set EMBED_PG_DSN=postgresql://food:foodpass@127.0.0.1:5433/food_helper
  python scripts/embedding/check_embedding_integrity.py

«Сироты» векторов при корректном FK не должны появляться; запрос оставлен как контроль.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for d in [here, *here.parents]:
        if (d / "docker-compose.yaml").exists():
            return d
    return here.parents[2]


ROOT = _repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.embedding.pg_dsn import connect_pg, resolve_pg_dsn


def main() -> None:
    ap = argparse.ArgumentParser(description="Счётчики recipes / recipe_embeddings.")
    ap.add_argument("--pg-dsn", default=None, help="DSN или EMBED_PG_DSN / DB_*")
    args = ap.parse_args()

    dsn = resolve_pg_dsn(args.pg_dsn)
    if not dsn:
        raise SystemExit(
            "Нужен --pg-dsn или EMBED_PG_DSN либо переменные DB_HOST, DB_USER, DB_PASSWORD, DB_NAME."
        )

    conn = connect_pg(dsn, retries=5, delay_s=1.0)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM recipes")
            n_recipes = int(cur.fetchone()[0])

            cur.execute("SELECT COUNT(*) FROM recipe_embeddings")
            n_emb = int(cur.fetchone()[0])

            cur.execute(
                """
                SELECT COUNT(*) FROM recipes r
                WHERE NOT EXISTS (
                  SELECT 1 FROM recipe_embeddings e WHERE e.recipe_id = r.id
                )
                """
            )
            n_missing = int(cur.fetchone()[0])

            cur.execute(
                """
                SELECT COUNT(*) FROM recipe_embeddings e
                WHERE NOT EXISTS (SELECT 1 FROM recipes r WHERE r.id = e.recipe_id)
                """
            )
            n_orphan = int(cur.fetchone()[0])
    finally:
        conn.close()

    print(f"recipes_total:              {n_recipes}")
    print(f"embeddings_total:           {n_emb}")
    print(f"recipes_missing_embedding:  {n_missing}")
    print(f"orphan_embeddings:        {n_orphan}  (ожидается 0 при FK)")


if __name__ == "__main__":
    main()
