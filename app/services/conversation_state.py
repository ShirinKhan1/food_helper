from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from psycopg2.extras import Json, RealDictCursor

from app.core.db import Database
from app.orchestrator.clarification import PendingClarification

_UNSET = object()


class ConversationAccessDenied(Exception):
    """Raised when the caller cannot use this conversation (maps to HTTP 404)."""


class UserMessageForkError(Exception):
    """Invalid edit_user_message_id or message is not a user row in this conversation."""


def _derive_title_from_message(content: str, *, max_len: int = 60) -> str:
    one_line = " ".join(content.split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 1] + "…"


@dataclass
class ConversationSnapshot:
    conversation_id: str
    last_recipe_results: list[int] = field(default_factory=list)
    selected_recipe_id: int | None = None
    last_event_profile: dict[str, Any] | None = None
    pending_clarification: PendingClarification | None = None


class ConversationStateService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def _get_session_owner_row(self, conversation_id: str) -> dict | None:
        with self._db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT conversation_id, user_id
                    FROM chat_sessions
                    WHERE conversation_id = %s::uuid
                    """,
                    (conversation_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def prepare_conversation(self, conversation_id: str | None, user_id: UUID | None) -> str:
        """
        Resolve or create a chat session for the given auth context.
        - New chat: conversation_id is None -> new UUID, insert with user_id.
        - Continue: conversation_id set -> row must exist and user_id must match policy.
        """
        if conversation_id is not None:
            cid = conversation_id.strip()
            row = self._get_session_owner_row(cid)
            if row is None:
                raise ConversationAccessDenied()
            session_uid = row.get("user_id")
            if user_id is not None:
                if session_uid is None or session_uid != user_id:
                    raise ConversationAccessDenied()
            else:
                if session_uid is not None:
                    raise ConversationAccessDenied()
            with self._db.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE chat_sessions SET updated_at = now()
                        WHERE conversation_id = %s::uuid
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

        cid = str(uuid4())
        with self._db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_sessions (conversation_id, user_id)
                    VALUES (%s::uuid, %s)
                    ON CONFLICT (conversation_id) DO UPDATE
                    SET updated_at = now()
                    """,
                    (cid, str(user_id) if user_id is not None else None),
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

    def export_state_json(self, conversation_id: str) -> dict[str, Any]:
        """Full `conversation_state.state` JSON for persisting on assistant rows."""
        return dict(self._load_state_dict(conversation_id))

    def fork_at_user_message(self, conversation_id: str, user_message_id: int) -> None:
        with self._db.connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, role
                    FROM chat_messages
                    WHERE id = %s AND conversation_id = %s::uuid
                    """,
                    (user_message_id, conversation_id),
                )
                row = cur.fetchone()
                if row is None or str(row.get("role") or "") != "user":
                    raise UserMessageForkError("User message not found in this conversation.")
                cur.execute(
                    """
                    SELECT state_after_turn
                    FROM chat_messages
                    WHERE conversation_id = %s::uuid AND role = 'assistant' AND id < %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (conversation_id, user_message_id),
                )
                prev = cur.fetchone()
                raw_snap = prev.get("state_after_turn") if prev else None
                if isinstance(raw_snap, dict):
                    restored = dict(raw_snap)
                else:
                    restored = {}
                cur.execute(
                    """
                    DELETE FROM chat_messages
                    WHERE conversation_id = %s::uuid AND id >= %s
                    """,
                    (conversation_id, user_message_id),
                )
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO conversation_state (conversation_id, state)
                    VALUES (%s::uuid, %s)
                    ON CONFLICT (conversation_id) DO UPDATE
                    SET state = EXCLUDED.state, updated_at = now()
                    """,
                    (conversation_id, Json(restored)),
                )
                cur.execute(
                    "UPDATE chat_sessions SET updated_at = now() WHERE conversation_id = %s::uuid",
                    (conversation_id,),
                )

    def append_message(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        state_after_turn: dict[str, Any] | None = None,
    ) -> int:
        with self._db.connection() as conn:
            with conn.cursor() as cur:
                if role == "assistant":
                    cur.execute(
                        """
                        INSERT INTO chat_messages (conversation_id, role, content, state_after_turn)
                        VALUES (%s::uuid, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            conversation_id,
                            role,
                            content,
                            Json(state_after_turn) if state_after_turn is not None else None,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO chat_messages (conversation_id, role, content)
                        VALUES (%s::uuid, %s, %s)
                        RETURNING id
                        """,
                        (conversation_id, role, content),
                    )
                inserted = cur.fetchone()
                msg_id = int(inserted[0]) if inserted else 0
                cur.execute(
                    "UPDATE chat_sessions SET updated_at = now() WHERE conversation_id = %s::uuid",
                    (conversation_id,),
                )
                if role == "user":
                    title = _derive_title_from_message(content)
                    cur.execute(
                        """
                        UPDATE chat_sessions
                        SET title = %s
                        WHERE conversation_id = %s::uuid AND title IS NULL
                        """,
                        (title, conversation_id),
                    )
        return msg_id

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
        raw_ep = state.get("last_event_profile")
        last_event_profile = raw_ep if isinstance(raw_ep, dict) else None
        return ConversationSnapshot(
            conversation_id=conversation_id,
            last_recipe_results=[
                int(item) for item in state.get("last_recipe_results", []) if item is not None
            ],
            selected_recipe_id=state.get("selected_recipe_id"),
            last_event_profile=last_event_profile,
            pending_clarification=pending,
        )

    def update_snapshot(
        self,
        conversation_id: str,
        *,
        last_recipe_results: list[int] | None = None,
        selected_recipe_id: int | None | object = _UNSET,
        last_event_profile: dict[str, Any] | None | object = _UNSET,
    ) -> None:
        state = self._load_state_dict(conversation_id)
        if last_recipe_results is not None:
            state["last_recipe_results"] = last_recipe_results
        if selected_recipe_id is not _UNSET:
            state["selected_recipe_id"] = selected_recipe_id
        if last_event_profile is not _UNSET:
            if last_event_profile is None:
                state.pop("last_event_profile", None)
            else:
                state["last_event_profile"] = last_event_profile
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
