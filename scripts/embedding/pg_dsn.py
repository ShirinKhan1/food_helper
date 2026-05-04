"""DSN и подключение к Postgres без тяжёлых зависимостей (sentence-transformers)."""
from __future__ import annotations

import os
import time


def resolve_pg_dsn(cli_value: str | None) -> str | None:
    if cli_value:
        return cli_value
    if os.getenv("EMBED_PG_DSN"):
        return os.environ["EMBED_PG_DSN"].strip()
    host = os.getenv("DB_HOST")
    if not host:
        return None
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "food_helper")
    user = os.getenv("DB_USER", "food")
    password = os.getenv("DB_PASSWORD", "foodpass")
    return f"host={host} port={port} dbname={name} user={user} password={password}"


def connect_pg(dsn: str, retries: int = 40, delay_s: float = 1.0):
    import psycopg2

    last_err: Exception | None = None
    for _ in range(retries):
        try:
            conn = psycopg2.connect(dsn)
            conn.autocommit = False
            return conn
        except Exception as e:
            last_err = e
            time.sleep(delay_s)
    raise RuntimeError(f"Could not connect to Postgres: {last_err}")
