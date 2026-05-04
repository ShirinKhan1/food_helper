from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.search.pg_vector_search import fetch_recipes_by_ids_ordered


def test_fetch_recipes_by_ids_ordered_preserves_rank_order() -> None:
    cur = MagicMock()
    cur.fetchall.return_value = [
        {"id": 2, "title": "B", "recipe_url": "b"},
        {"id": 3, "title": "C", "recipe_url": "c"},
        {"id": 1, "title": "A", "recipe_url": "a"},
    ]
    out = fetch_recipes_by_ids_ordered(
        cur,
        [3, 1, 2],
        scores_by_id={3: 0.1, 1: 0.2, 2: 0.3},
    )
    assert [r["id"] for r in out] == [3, 1, 2]
    assert out[0]["similarity"] == pytest.approx(0.9)
    assert out[0]["cosine_distance"] == pytest.approx(0.1)


def test_fetch_recipes_skips_missing_ids() -> None:
    cur = MagicMock()
    cur.fetchall.return_value = [{"id": 1, "title": "A", "recipe_url": "a"}]
    out = fetch_recipes_by_ids_ordered(
        cur,
        [1, 999],
        scores_by_id={1: 0.0, 999: 0.5},
    )
    assert len(out) == 1
    assert out[0]["id"] == 1


def test_fetch_empty_ids() -> None:
    cur = MagicMock()
    assert fetch_recipes_by_ids_ordered(cur, []) == []
    cur.execute.assert_not_called()
