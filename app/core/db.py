from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from psycopg2.extras import RealDictCursor

from scripts.embedding.pg_dsn import connect_pg


class DatabaseUnavailableError(RuntimeError):
    """Raised when the API cannot connect to Postgres."""


class Database:
    def __init__(self, dsn: str | None) -> None:
        self._dsn = dsn

    @contextmanager
    def connection(self) -> Iterator:
        if not self._dsn:
            raise DatabaseUnavailableError(
                "Database DSN is not configured. Set APP_PG_DSN or DB_* variables."
            )

        try:
            conn = connect_pg(self._dsn, retries=1, delay_s=0.1)
        except Exception as exc:  # pragma: no cover - exercised in API tests with monkeypatch
            raise DatabaseUnavailableError(f"Could not connect to Postgres: {exc}") from exc

        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ping(self) -> str:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return "ok"

    @contextmanager
    def dict_cursor(self):
        with self.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
