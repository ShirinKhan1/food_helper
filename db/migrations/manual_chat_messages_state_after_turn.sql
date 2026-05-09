-- Apply manually on existing DBs (init db uses 01_schema.sql for fresh volumes).
ALTER TABLE chat_messages
  ADD COLUMN IF NOT EXISTS state_after_turn JSONB;
