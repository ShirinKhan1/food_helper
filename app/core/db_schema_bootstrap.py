"""Idempotent DDL for DBs created before new columns were added to init SQL."""
from __future__ import annotations

import logging

from app.core.db import Database, DatabaseUnavailableError

LOGGER = logging.getLogger(__name__)


def ensure_schema(db: Database) -> None:
    try:
        with db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS state_after_turn JSONB"
                )
    except DatabaseUnavailableError:
        LOGGER.warning("Database unavailable; skipping schema bootstrap.")
    except Exception as exc:
        LOGGER.warning("Schema bootstrap failed (chat may error until DDL is applied): %s", exc)
