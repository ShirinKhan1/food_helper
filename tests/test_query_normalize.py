from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.search.query_normalize import normalize_query_for_search


def test_normalize_empty() -> None:
    assert normalize_query_for_search("") == ""
    assert normalize_query_for_search("   ") == ""


def test_normalize_removes_stopwords_and_lemmatizes() -> None:
    out = normalize_query_for_search("хочу борщ с мясом")
    assert "хочу" not in out.split()
    assert "борщ" in out
    assert "мясо" in out


def test_normalize_fallback_when_only_stopwords() -> None:
    # после фильтра пусто → лёгкая очистка исходника
    raw = "и   в  но"
    assert normalize_query_for_search(raw) == "и в но"


def test_normalize_cyrillic_preserved() -> None:
    out = normalize_query_for_search("Ёжики  и  грибы")
    assert "ёжик" in out.lower() or "ежик" in out.lower()
    assert "гриб" in out.lower()
