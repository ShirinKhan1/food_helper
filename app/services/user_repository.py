from __future__ import annotations

from uuid import UUID
from psycopg2.extras import RealDictCursor

from app.core.db import Database
from app.models.user import User


def normalize_email(email: str) -> str:
    return email.strip().lower()


class UserRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create_user(self, email: str, password_hash: str) -> User:
        norm = normalize_email(email)
        with self._db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO users (email, password_hash)
                    VALUES (%s, %s)
                    RETURNING id, email, created_at
                    """,
                    (norm, password_hash),
                )
                row = cur.fetchone()
        assert row is not None
        return User(
            id=row["id"],
            email=row["email"],
            created_at=row["created_at"],
        )

    def get_by_email(self, email: str) -> User | None:
        norm = normalize_email(email)
        with self._db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, email, created_at
                    FROM users
                    WHERE lower(email) = %s
                    """,
                    (norm,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return User(id=row["id"], email=row["email"], created_at=row["created_at"])

    def get_by_id(self, user_id: UUID) -> User | None:
        with self._db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, email, created_at
                    FROM users
                    WHERE id = %s::uuid
                    """,
                    (str(user_id),),
                )
                row = cur.fetchone()
        if not row:
            return None
        return User(id=row["id"], email=row["email"], created_at=row["created_at"])

    def get_password_hash_by_email(self, email: str) -> tuple[UUID, str] | None:
        norm = normalize_email(email)
        with self._db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, password_hash
                    FROM users
                    WHERE lower(email) = %s
                    """,
                    (norm,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return row["id"], row["password_hash"]
