from __future__ import annotations

from uuid import UUID

from psycopg2.extras import RealDictCursor

from app.core.db import Database


class ChatHistoryRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def list_chats(self, user_id: UUID) -> list[dict]:
        with self._db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT conversation_id, title, created_at, updated_at
                    FROM chat_sessions
                    WHERE user_id = %s::uuid
                    ORDER BY updated_at DESC
                    """,
                    (str(user_id),),
                )
                rows = cur.fetchall() or []
        return [dict(r) for r in rows]

    def get_chat_with_messages(self, user_id: UUID, conversation_id: UUID) -> dict | None:
        with self._db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT conversation_id, title, created_at, updated_at
                    FROM chat_sessions
                    WHERE conversation_id = %s::uuid AND user_id = %s::uuid
                    """,
                    (str(conversation_id), str(user_id)),
                )
                session = cur.fetchone()
                if not session:
                    return None
                cur.execute(
                    """
                    SELECT id, role, content, created_at
                    FROM chat_messages
                    WHERE conversation_id = %s::uuid
                    ORDER BY created_at ASC
                    """,
                    (str(conversation_id),),
                )
                messages = cur.fetchall() or []
        return {
            "session": dict(session),
            "messages": [dict(m) for m in messages],
        }

    def update_title(self, user_id: UUID, conversation_id: UUID, title: str) -> dict | None:
        with self._db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE chat_sessions
                    SET title = %s, updated_at = now()
                    WHERE conversation_id = %s::uuid AND user_id = %s::uuid
                    RETURNING conversation_id, title, updated_at
                    """,
                    (title, str(conversation_id), str(user_id)),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def delete_chat(self, user_id: UUID, conversation_id: UUID) -> bool:
        with self._db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM chat_sessions
                    WHERE conversation_id = %s::uuid AND user_id = %s::uuid
                    """,
                    (str(conversation_id), str(user_id)),
                )
                return cur.rowcount > 0
