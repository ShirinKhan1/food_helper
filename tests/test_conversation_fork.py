from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import pytest

from app.services.conversation_state import ConversationStateService, UserMessageForkError


class _MockCursor:
    def __init__(self, fetch_sequence: list[dict[str, Any] | None]) -> None:
        self.fetch_sequence = list(fetch_sequence)
        self.actions: list[tuple[str, tuple[Any, ...] | None]] = []

    def __enter__(self) -> _MockCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        self.actions.append((query, params))

    def fetchone(self) -> dict[str, Any] | None:
        if not self.fetch_sequence:
            return None
        return self.fetch_sequence.pop(0)


class _MockConn:
    def __init__(self, cursors: list[_MockCursor]) -> None:
        self._cursors = cursors
        self._idx = 0

    def cursor(self, cursor_factory: Any = None) -> _MockCursor:
        cur = self._cursors[self._idx]
        self._idx += 1
        return cur

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


class _MockDB:
    def __init__(self, conn: _MockConn) -> None:
        self._conn = conn

    @contextmanager
    def connection(self) -> Any:
        yield self._conn


def test_fork_at_user_message_restores_and_deletes() -> None:
    cid = str(uuid4())
    cur1 = _MockCursor(
        [
            {"id": 50, "role": "user"},
            {"state_after_turn": {"last_recipe_results": [7, 8]}},
        ],
    )
    cur2 = _MockCursor([])
    svc = ConversationStateService(_MockDB(_MockConn([cur1, cur2])))
    svc.fork_at_user_message(cid, 50)

    deletes = [a for a in cur1.actions if "DELETE FROM chat_messages" in a[0]]
    assert len(deletes) == 1
    assert deletes[0][1] == (cid, 50)

    upserts = [a for a in cur2.actions if "conversation_state" in a[0]]
    assert len(upserts) == 1
    _q, params = upserts[0]
    assert params is not None
    assert params[0] == cid
    state_param = params[1]
    adapted = getattr(state_param, "adapted", state_param)
    assert adapted == {"last_recipe_results": [7, 8]}


def test_fork_at_user_message_uses_empty_state_when_no_snapshot() -> None:
    cid = str(uuid4())
    cur1 = _MockCursor(
        [
            {"id": 1, "role": "user"},
            {"state_after_turn": None},
        ],
    )
    cur2 = _MockCursor([])
    svc = ConversationStateService(_MockDB(_MockConn([cur1, cur2])))
    svc.fork_at_user_message(cid, 1)
    upserts = [a for a in cur2.actions if "conversation_state" in a[0]]
    state_param = upserts[0][1][1]
    adapted = getattr(state_param, "adapted", state_param)
    assert adapted == {}


def test_fork_at_user_message_raises_when_missing() -> None:
    cid = str(uuid4())
    cur1 = _MockCursor([None])
    cur2 = _MockCursor([])
    svc = ConversationStateService(_MockDB(_MockConn([cur1, cur2])))
    with pytest.raises(UserMessageForkError):
        svc.fork_at_user_message(cid, 99)


def test_fork_at_user_message_raises_when_not_user() -> None:
    cid = str(uuid4())
    cur1 = _MockCursor([{"id": 2, "role": "assistant"}])
    cur2 = _MockCursor([])
    svc = ConversationStateService(_MockDB(_MockConn([cur1, cur2])))
    with pytest.raises(UserMessageForkError):
        svc.fork_at_user_message(cid, 2)
