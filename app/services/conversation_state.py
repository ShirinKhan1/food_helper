from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from psycopg2.extras import Json, RealDictCursor

from app.core.db import Database
from app.orchestrator.clarification import PendingClarification

_UNSET = object()


@dataclass
class ConversationSnapshot:
    conversation_id: str
    last_recipe_results: list[int] = field(default_factory=list)
    selected_recipe_id: int | None = None
    pending_clarification: PendingClarification | None = None


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

    def _load_state_dict(self, conversation_id: str) -> dict[str, Any]:
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
        return dict(state)

    def _write_state_dict(self, conversation_id: str, state: dict[str, Any]) -> None:
        with self._db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO conversation_state (conversation_id, state)
                    VALUES (%s::uuid, %s)
                    ON CONFLICT (conversation_id) DO UPDATE
                    SET state = EXCLUDED.state, updated_at = now()
                    """,
                    (conversation_id, Json(state)),
                )

    def get_snapshot(self, conversation_id: str) -> ConversationSnapshot:
        state = self._load_state_dict(conversation_id)
        pending = None
        raw_pending = state.get("pending_clarification")
        if isinstance(raw_pending, dict):
            try:
                pending = PendingClarification.model_validate(raw_pending)
            except Exception:
                pending = None
        return ConversationSnapshot(
            conversation_id=conversation_id,
            last_recipe_results=[
                int(item) for item in state.get("last_recipe_results", []) if item is not None
            ],
            selected_recipe_id=state.get("selected_recipe_id"),
            pending_clarification=pending,
        )

    def update_snapshot(
        self,
        conversation_id: str,
        *,
        last_recipe_results: list[int] | None = None,
        selected_recipe_id: int | None | object = _UNSET,
    ) -> None:
        state = self._load_state_dict(conversation_id)
        if last_recipe_results is not None:
            state["last_recipe_results"] = last_recipe_results
        if selected_recipe_id is not _UNSET:
            state["selected_recipe_id"] = selected_recipe_id
        self._write_state_dict(conversation_id, state)

    def get_pending_clarification(self, conversation_id: str) -> PendingClarification | None:
        return self.get_snapshot(conversation_id).pending_clarification

    def set_pending_clarification(self, conversation_id: str, clarification: PendingClarification) -> None:
        state = self._load_state_dict(conversation_id)
        state["pending_clarification"] = clarification.model_dump(mode="json")
        self._write_state_dict(conversation_id, state)

    def clear_pending_clarification(self, conversation_id: str) -> None:
        state = self._load_state_dict(conversation_id)
        state.pop("pending_clarification", None)
        self._write_state_dict(conversation_id, state)

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

    def get_recent_messages(self, conversation_id: str, *, limit: int = 6) -> list[tuple[str, str]]:
        with self._db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT role, content
                    FROM chat_messages
                    WHERE conversation_id = %s::uuid
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (conversation_id, limit),
                )
                rows = cur.fetchall() or []
        return [(str(row.get("role") or ""), str(row.get("content") or "")) for row in reversed(rows)]
