-- Postgres init: runs only on first volume creation (empty data dir).
-- If pgdata already exists, apply new DDL manually, e.g.:
--   docker compose exec -T db psql -U food -d food_helper -f - < db/migrations/manual_pgvector_embeddings.sql

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

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

CREATE TABLE IF NOT EXISTS users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email           TEXT NOT NULL UNIQUE,
  password_hash   TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS users_email_idx ON users (lower(email));

CREATE TABLE IF NOT EXISTS chat_sessions (
  conversation_id UUID PRIMARY KEY,
  user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
  title           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_sessions_user_updated_idx
  ON chat_sessions (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
  id              BIGSERIAL PRIMARY KEY,
  conversation_id UUID NOT NULL REFERENCES chat_sessions(conversation_id) ON DELETE CASCADE,
  role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content         TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_messages_conversation_idx
  ON chat_messages (conversation_id, created_at);

CREATE TABLE IF NOT EXISTS conversation_state (
  conversation_id UUID PRIMARY KEY REFERENCES chat_sessions(conversation_id) ON DELETE CASCADE,
  state           JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
