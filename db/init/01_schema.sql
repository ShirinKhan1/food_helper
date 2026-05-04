-- Postgres init: runs only on first volume creation (empty data dir).
-- If pgdata already exists, apply new DDL manually, e.g.:
--   docker compose exec -T db psql -U food -d food_helper -f - < db/migrations/manual_pgvector_embeddings.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS recipes (
  id              BIGSERIAL PRIMARY KEY,
  recipe_url      TEXT UNIQUE NOT NULL,
  source          TEXT,
  title           TEXT,
  description     TEXT,
  servings        INT,
  category        TEXT,
  subcategory     TEXT,
  subcategory_url TEXT,
  afterword       TEXT,

  calories_kcal   NUMERIC,
  protein_g       NUMERIC,
  fat_g           NUMERIC,
  carbs_g         NUMERIC,

  nutrition       JSONB,
  properties      JSONB,
  ingredients     JSONB,
  steps           JSONB,
  raw             JSONB NOT NULL,

  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS recipes_title_idx ON recipes USING GIN (to_tsvector('russian', coalesce(title,'')));
CREATE INDEX IF NOT EXISTS recipes_raw_gin_idx ON recipes USING GIN (raw);

-- Векторы: размерность 384 под intfloat/multilingual-e5-small (см. scripts/embedding/embed_recipes.py).
-- Другая модель с иной размерностью потребует смены типа колонки или новой таблицы/миграции.
CREATE TABLE IF NOT EXISTS recipe_embeddings (
  recipe_id   BIGINT PRIMARY KEY REFERENCES recipes(id) ON DELETE CASCADE,
  model       TEXT NOT NULL,
  embedding   vector(384) NOT NULL,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS recipe_embeddings_hnsw_idx
  ON recipe_embeddings USING hnsw (embedding vector_cosine_ops);
