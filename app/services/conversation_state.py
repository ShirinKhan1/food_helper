from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from psycopg2.extras import Json, RealDictCursor

from app.core.db import Database

_UNSET = object()


@dataclass
class ConversationSnapshot:
    conversation_id: str
    last_recipe_results: list[int] = field(default_factory=list)
    selected_recipe_id: int | None = None


class ConversationStateService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def ensure_conversation(self, conversation_id: str | None) -> str:
        cid = conversation_id or str(uuid4())
        with self._db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_sessions (conversation_id)
                    VALUES (%s::uuid)
                    ON CONFLICT (conversation_id) DO UPDATE
                    SET updated_at = now()
                    """,
                    (cid,),
                )
                cur.execute(
                    """
                    INSERT INTO conversation_state (conversation_id, state)
                    VALUES (%s::uuid, '{}'::jsonb)
                    ON CONFLICT (conversation_id) DO NOTHING
                    """,
                    (cid,),
                )
        return cid

    def append_message(self, conversation_id: str, *, role: str, content: str) -> None:
        with self._db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_messages (conversation_id, role, content)
                    VALUES (%s::uuid, %s, %s)
                    """,
                    (conversation_id, role, content),
                )
                cur.execute(
                    "UPDATE chat_sessions SET updated_at = now() WHERE conversation_id = %s::uuid",
                    (conversation_id,),
                )

    def get_snapshot(self, conversation_id: str) -> ConversationSnapshot:
        with self._db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT state
                    FROM conversation_state
                    WHERE conversation_id = %s::uuid
                    """,
                    (conversation_id,),
                )
                row = cur.fetchone()

        state = row["state"] if row and isinstance(row.get("state"), dict) else {}
        return ConversationSnapshot(
            conversation_id=conversation_id,
            last_recipe_results=[
                int(item) for item in state.get("last_recipe_results", []) if item is not None
            ],
            selected_recipe_id=state.get("selected_recipe_id"),
        )

    def update_snapshot(
        self,
        conversation_id: str,
        *,
        last_recipe_results: list[int] | None = None,
        selected_recipe_id: int | None | object = _UNSET,
    ) -> None:
        snapshot = self.get_snapshot(conversation_id)
        if last_recipe_results is not None:
            snapshot.last_recipe_results = last_recipe_results
        if selected_recipe_id is not _UNSET:
            snapshot.selected_recipe_id = selected_recipe_id

        payload = {
            "last_recipe_results": snapshot.last_recipe_results,
            "selected_recipe_id": snapshot.selected_recipe_id,
        }
        with self._db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO conversation_state (conversation_id, state)
                    VALUES (%s::uuid, %s)
                    ON CONFLICT (conversation_id) DO UPDATE
                    SET state = EXCLUDED.state, updated_at = now()
                    """,
                    (conversation_id, Json(payload)),
                )

    def resolve_reference(self, conversation_id: str, reference: dict | None) -> int | None:
        snapshot = self.get_snapshot(conversation_id)
        if not reference:
            return snapshot.selected_recipe_id

        ref_type = reference.get("type")
        if ref_type == "rank":
            rank = int(reference.get("value"))
            if 1 <= rank <= len(snapshot.last_recipe_results):
                return snapshot.last_recipe_results[rank - 1]
            return None
        if ref_type == "selected":
            return snapshot.selected_recipe_id
        return None
