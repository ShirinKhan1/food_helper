# tests/test_embed_recipes.py
from __future__ import annotations

import json
from pathlib import Path
import pytest
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.embedding.embed_recipes import (
    EmbedConfig,
    embed_recipes_to_json,
    load_recipes,
    recipe_to_passage,
)
from scripts.embedding.pg_dsn import resolve_pg_dsn


def test_resolve_pg_dsn_explicit_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DB_HOST", "wrong-host")
    monkeypatch.setenv("EMBED_PG_DSN", "postgresql://u:p@explicit:5432/db")
    assert resolve_pg_dsn("postgresql://cli:pw@cli-host:5432/mydb") == "postgresql://cli:pw@cli-host:5432/mydb"
    assert resolve_pg_dsn(None) == "postgresql://u:p@explicit:5432/db"


def test_resolve_pg_dsn_from_db_host_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EMBED_PG_DSN", raising=False)
    monkeypatch.setenv("DB_HOST", "db.internal")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_NAME", "food_helper")
    monkeypatch.setenv("DB_USER", "food")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    dsn = resolve_pg_dsn(None)
    assert "host=db.internal" in dsn
    assert "port=5433" in dsn
    assert "dbname=food_helper" in dsn
    assert "user=food" in dsn
    assert "password=secret" in dsn


def test_load_recipes_json_array(tmp_path: Path) -> None:
    data = [
        {"title": "A", "ingredients": [{"name": "Мука"}]},
        {"title": "B", "ingredients": [{"name": "Яйцо"}]},
    ]
    p = tmp_path / "recipes.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    loaded = load_recipes(p)
    assert isinstance(loaded, list)
    assert len(loaded) == 2
    assert loaded[0]["title"] == "A"


def test_load_recipes_jsonl(tmp_path: Path) -> None:
    lines = [
        json.dumps({"title": "A"}, ensure_ascii=False),
        json.dumps({"title": "B"}, ensure_ascii=False),
    ]
    p = tmp_path / "recipes.jsonl"
    p.write_text("\n".join(lines), encoding="utf-8")

    loaded = load_recipes(p)
    assert len(loaded) == 2
    assert loaded[1]["title"] == "B"


def test_recipe_to_passage_has_prefix_and_content() -> None:
    r = {
        "title": "Пицца",
        "description": "Быстро",
        "ingredients": [{"block": "Для теста", "name": "Мука"}],
        "properties": {"Кухня": "итальянская", "Будет готово через": "20 минут"},
    }
    txt = recipe_to_passage(r, include_properties=True)
    assert txt.startswith("passage: ")
    assert "Название: Пицца" in txt
    assert "Ингредиенты:" in txt
    assert "Свойства:" in txt


@pytest.mark.parametrize(
    "model_name",
    [
        # маленькая модель для тестов (быстрее качается), но код должен работать с любой
        "sentence-transformers/paraphrase-MiniLM-L3-v2",
    ],
)
def test_embeddings_json_shape_and_norm(tmp_path: Path, model_name: str) -> None:
    recipes = [
        {
            "recipe_url": "https://example.com/1",
            "title": "Омлет",
            "description": "На завтрак",
            "ingredients": [{"name": "Яйцо"}, {"name": "Молоко"}],
            "properties": {"Будет готово через": "10 минут", "Кухня": "домашняя"},
        },
        {
            "recipe_url": "https://example.com/2",
            "title": "Салат",
            "description": "Лёгкий",
            "ingredients": [{"name": "Огурец"}, {"name": "Помидор"}],
        },
    ]

    out = tmp_path / "embeddings.json"
    cfg = EmbedConfig(model_name=model_name, batch_size=2, normalize=True)
    result = embed_recipes_to_json(recipes, out, cfg)

    assert out.exists()
    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert parsed["model"] == model_name
    assert parsed["embedding_dim"] > 0
    assert len(parsed["items"]) == 2

    dim = parsed["embedding_dim"]
    v0 = parsed["items"][0]["vector"]
    assert isinstance(v0, list)
    assert len(v0) == dim
    assert all(isinstance(x, (int, float)) for x in v0)

    # при normalize=True длина вектора должна быть близка к 1
    import math

    norm = math.sqrt(sum(float(x) * float(x) for x in v0))
    assert abs(norm - 1.0) < 1e-3


def test_embeddings_deterministic_on_same_text(tmp_path: Path) -> None:
    recipes = [
        {"recipe_url": "x", "title": "Тост", "description": "Хлеб и сыр", "ingredients": [{"name": "Хлеб"}]},
    ]
    out1 = tmp_path / "e1.json"
    out2 = tmp_path / "e2.json"

    cfg = EmbedConfig(
        # чтобы не зависеть от E5 префиксов в тесте — любая модель SentenceTransformer
        model_name="sentence-transformers/paraphrase-MiniLM-L3-v2",
        batch_size=1,
        normalize=True,
    )

    r1 = embed_recipes_to_json(recipes, out1, cfg)
    r2 = embed_recipes_to_json(recipes, out2, cfg)

    v1 = r1["items"][0]["vector"]
    v2 = r2["items"][0]["vector"]

    # допускаем микроскопические расхождения float
    assert len(v1) == len(v2)
    max_abs = max(abs(a - b) for a, b in zip(v1, v2))
    assert max_abs < 1e-6
