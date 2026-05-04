-- Применить вручную к существующей БД (том pgdata уже создан, init не перезапустится):
-- docker compose exec -T db psql -U food -d food_helper -f /path/in/container
-- или с хоста: Get-Content db/migrations/manual_pgvector_embeddings.sql | docker compose exec -T db psql -U food -d food_helper

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS recipe_embeddings (
  recipe_id   BIGINT PRIMARY KEY REFERENCES recipes(id) ON DELETE CASCADE,
  model       TEXT NOT NULL,
  embedding   vector(384) NOT NULL,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS recipe_embeddings_hnsw_idx
  ON recipe_embeddings USING hnsw (embedding vector_cosine_ops);
