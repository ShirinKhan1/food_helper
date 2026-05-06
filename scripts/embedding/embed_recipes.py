# scripts/embedding/embed_recipes.py — фаза 0: векторы в Postgres
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for d in [here, *here.parents]:
        if (d / "docker-compose.yaml").exists():
            return d
    return here.parents[2]


_ROOT = _repo_root()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np
from sentence_transformers import SentenceTransformer

from scripts.embedding.pg_dsn import connect_pg, resolve_pg_dsn

# Колонка recipe_embeddings.embedding — vector(384) под intfloat/multilingual-e5-small
EXPECTED_EMBEDDING_DIM = 384


def _reset_hf_http_session() -> None:
    """
    huggingface_hub в новых версиях использует httpx и имеет close_session().
    В старых версиях было reset_sessions() на requests-сессиях.
    Делаем максимально совместимо.
    """
    try:
        from huggingface_hub import close_session

        close_session()
        return
    except Exception:
        pass

    try:
        from huggingface_hub.utils._http import reset_sessions  # type: ignore

        reset_sessions()
    except Exception:
        pass


def _is_closed_client_error(e: Exception) -> bool:
    return "client has been closed" in str(e).lower()


def _retry_once_on_closed_client(fn):
    try:
        return fn()
    except RuntimeError as e:
        if _is_closed_client_error(e):
            _reset_hf_http_session()
            return fn()
        raise


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_recipes(path: str | Path) -> List[Dict[str, Any]]:
    """
    Поддерживает:
      - JSON-массив: [ {...}, {...} ]
      - JSONL: по одному JSON-объекту в строке
    """
    p = Path(path)
    raw = _read_text(p).lstrip()

    if not raw:
        return []

    if raw[0] == "[":
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("Ожидался JSON-массив рецептов.")
        return data

    recipes: List[Dict[str, Any]] = []
    for i, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"Некорректный JSON на строке {i}: {e}") from e
        if not isinstance(obj, dict):
            raise ValueError(f"JSONL строка {i} должна быть объектом.")
        recipes.append(obj)

    return recipes


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    s = str(x)
    return " ".join(s.split())


def _format_ingredients(ingredients: Any) -> str:
    if not isinstance(ingredients, list):
        return ""

    parts: List[str] = []
    for ing in ingredients:
        if not isinstance(ing, dict):
            continue
        name = _safe_str(ing.get("name"))
        block = _safe_str(ing.get("block"))
        if not name:
            continue
        parts.append(f"{block}: {name}" if block else name)

    return ", ".join(parts)


def recipe_to_passage(
    r: Dict[str, Any],
    *,
    include_properties: bool = True,
    include_afterword: bool = False,
) -> str:
    title = _safe_str(r.get("title"))
    desc = _safe_str(r.get("description"))
    ing = _format_ingredients(r.get("ingredients"))

    chunks: List[str] = []
    if title:
        chunks.append(f"Название: {title}")
    if desc:
        chunks.append(f"Описание: {desc}")
    if ing:
        chunks.append(f"Ингредиенты: {ing}")

    if include_properties:
        props = r.get("properties")
        if isinstance(props, dict) and props:
            keep = [
                "Будет готово через",
                "Время на кухне",
                "Сложность",
                "Кухня",
                "Аллергены",
            ]
            pchunks = []
            for k in keep:
                v = props.get(k)
                if v:
                    pchunks.append(f"{k}: {_safe_str(v)}")
            if pchunks:
                chunks.append("Свойства: " + "; ".join(pchunks))

    if include_afterword:
        after = _safe_str(r.get("afterword"))
        if after:
            chunks.append(f"Примечание: {after}")

    body = "\n".join(chunks).strip()
    return "passage: " + body


def get_recipe_id(r: Dict[str, Any], fallback_index: int) -> str:
    return (
        _safe_str(r.get("recipe_url"))
        or _safe_str(r.get("source"))
        or f"idx:{fallback_index}"
    )


def build_payload(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": r.get("title"),
        "recipe_url": r.get("recipe_url"),
        "servings": r.get("servings"),
        "properties": r.get("properties"),
    }


@dataclass(frozen=True)
class EmbedConfig:
    model_name: str = "intfloat/multilingual-e5-small"
    model_path: Optional[str] = None
    batch_size: int = 32
    normalize: bool = True
    max_seq_length: int = 512
    include_properties: bool = True
    include_afterword: bool = False


def _load_sentence_model(cfg: EmbedConfig) -> SentenceTransformer:
    _reset_hf_http_session()
    model_source = cfg.model_path or cfg.model_name
    model = _retry_once_on_closed_client(
        lambda: SentenceTransformer(model_source, device="cpu")
    )
    model.max_seq_length = cfg.max_seq_length
    return model


def encode_recipe_vectors(
    recipes: List[Dict[str, Any]],
    cfg: EmbedConfig,
    *,
    model: SentenceTransformer | None = None,
) -> Tuple[List[Dict[str, Any]], np.ndarray]:
    """
    Возвращает items (как для JSON) и матрицу векторов float32 [N, dim].
    """
    m = model or _load_sentence_model(cfg)

    texts: List[str] = [
        recipe_to_passage(
            r,
            include_properties=cfg.include_properties,
            include_afterword=cfg.include_afterword,
        )
        for r in recipes
    ]

    vectors = _retry_once_on_closed_client(
        lambda: m.encode(
            texts,
            batch_size=cfg.batch_size,
            show_progress_bar=True,
            normalize_embeddings=cfg.normalize,
        )
    )
    arr = np.asarray(vectors, dtype=np.float32)

    items: List[Dict[str, Any]] = []
    for i, r in enumerate(recipes):
        rid = get_recipe_id(r, i)
        vec = arr[i].tolist()
        items.append({"id": rid, "vector": vec, "payload": build_payload(r)})

    return items, arr


def embed_recipes_to_json(
    recipes: List[Dict[str, Any]],
    out_path: str | Path,
    cfg: EmbedConfig = EmbedConfig(),
) -> Dict[str, Any]:
    items, _arr = encode_recipe_vectors(recipes, cfg)

    result = {
        "model": cfg.model_name,
        "embedding_dim": int(len(items[0]["vector"])) if items else 0,
        "normalize": cfg.normalize,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }

    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _register_pgvector(conn) -> None:
    from pgvector.psycopg2 import register_vector

    register_vector(conn)


def _raw_to_recipe_dict(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)  # Json from psycopg2


def fetch_recipe_batch_from_db(
    cur,
    *,
    last_id: int,
    limit: int,
    only_missing: bool,
) -> List[Tuple[int, Dict[str, Any]]]:
    if only_missing:
        cur.execute(
            """
            SELECT r.id, r.raw
            FROM recipes r
            LEFT JOIN recipe_embeddings e ON e.recipe_id = r.id
            WHERE r.id > %s AND e.recipe_id IS NULL
            ORDER BY r.id
            LIMIT %s
            """,
            (last_id, limit),
        )
    else:
        cur.execute(
            """
            SELECT r.id, r.raw
            FROM recipes r
            WHERE r.id > %s
            ORDER BY r.id
            LIMIT %s
            """,
            (last_id, limit),
        )
    rows = cur.fetchall()
    out: List[Tuple[int, Dict[str, Any]]] = []
    for rid, raw in rows:
        out.append((int(rid), _raw_to_recipe_dict(raw)))
    return out


def map_urls_to_recipe_ids(cur, urls: Sequence[str]) -> Dict[str, int]:
    if not urls:
        return {}
    cur.execute(
        "SELECT recipe_url, id FROM recipes WHERE recipe_url = ANY(%s)",
        (list(urls),),
    )
    return {str(u): int(i) for u, i in cur.fetchall()}


def upsert_embeddings(
    cur,
    model_name: str,
    rows: List[Tuple[int, List[float]]],
    *,
    expected_dim: int = EXPECTED_EMBEDDING_DIM,
) -> int:
    if not rows:
        return 0
    dim = len(rows[0][1])
    if dim != expected_dim:
        raise ValueError(
            f"Размерность вектора {dim} не совпадает с ожидаемой {expected_dim} "
            f"(колонка vector({expected_dim}) в recipe_embeddings)."
        )
    sql = """
    INSERT INTO recipe_embeddings (recipe_id, model, embedding)
    VALUES (%s, %s, %s)
    ON CONFLICT (recipe_id) DO UPDATE SET
      embedding = EXCLUDED.embedding,
      model = EXCLUDED.model,
      updated_at = now()
    """
    for rid, vec in rows:
        cur.execute(sql, (rid, model_name, vec))
    return len(rows)


def embed_to_postgres(
    recipes: List[Dict[str, Any]],
    vectors: np.ndarray,
    cfg: EmbedConfig,
    conn,
    *,
    db_ids: Optional[List[Optional[int]]] = None,
) -> Tuple[int, int]:
    """
    db_ids: параллельно recipes — если задан, upsert по recipe_id; иначе поиск id по recipe_url/source.
    Возвращает (upserted_count, skipped_no_id_count).
    """
    _register_pgvector(conn)
    n = len(recipes)
    if vectors.shape[0] != n:
        raise ValueError("Число векторов не совпадает с числом рецептов.")

    skipped = 0
    to_write: List[Tuple[int, List[float]]] = []

    if db_ids is not None:
        if len(db_ids) != n:
            raise ValueError("db_ids должен совпадать по длине с recipes.")
        for i, rid in enumerate(db_ids):
            if rid is None:
                skipped += 1
                continue
            to_write.append((int(rid), vectors[i].tolist()))
    else:
        keys: List[str] = []
        for i, r in enumerate(recipes):
            keys.append(get_recipe_id(r, i))
        real_urls = [k for k in keys if not k.startswith("idx:")]
        with conn.cursor() as cur:
            url_map = map_urls_to_recipe_ids(cur, real_urls)
        for i, k in enumerate(keys):
            if k.startswith("idx:"):
                skipped += 1
                continue
            rid = url_map.get(k)
            if rid is None:
                skipped += 1
                continue
            to_write.append((rid, vectors[i].tolist()))

    if not to_write:
        conn.commit()
        return 0, skipped

    with conn.cursor() as cur:
        upsert_embeddings(cur, cfg.model_name, to_write)
    conn.commit()
    return len(to_write), skipped


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Эмбеддинги рецептов: JSON и/или Postgres (pgvector)."
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", help="Путь к recipes.json или recipes.jsonl")
    src.add_argument(
        "--from-db",
        action="store_true",
        help="Читать рецепты из Postgres (колонка raw), нужен --pg-dsn или EMBED_PG_DSN / DB_*",
    )
    ap.add_argument(
        "--output",
        default=None,
        help="Путь к embeddings.json (опционально, если пишем в БД)",
    )
    ap.add_argument(
        "--pg-dsn",
        default=None,
        help="Строка подключения psycopg2 или переменная EMBED_PG_DSN / DB_HOST,...",
    )
    ap.add_argument(
        "--model",
        default=os.getenv("EMBED_MODEL_NAME", EmbedConfig.model_name),
        help="Название модели HF",
    )
    ap.add_argument(
        "--model-path",
        default=os.getenv("EMBED_MODEL_PATH") or None,
        help="Локальный путь к SentenceTransformer; в БД/JSON всё равно пишется --model",
    )
    ap.add_argument("--batch-size", type=int, default=EmbedConfig.batch_size)
    ap.add_argument("--no-normalize", action="store_true", help="Не нормализовать эмбеддинги")
    ap.add_argument("--max-seq-length", type=int, default=EmbedConfig.max_seq_length)
    ap.add_argument("--no-properties", action="store_true", help="Не добавлять properties в текст")
    ap.add_argument("--include-afterword", action="store_true", help="Добавить afterword в текст")
    ap.add_argument(
        "--db-fetch-batch",
        type=int,
        default=500,
        help="Сколько строк recipes забирать из БД за один SELECT (--from-db)",
    )
    ap.add_argument(
        "--only-missing",
        action="store_true",
        help="Только рецепты без строки в recipe_embeddings (только с --from-db)",
    )
    args = ap.parse_args()

    if args.only_missing and not args.from_db:
        ap.error("--only-missing допустим только вместе с --from-db")

    dsn = resolve_pg_dsn(args.pg_dsn)
    if args.from_db and not dsn:
        ap.error("--from-db требует --pg-dsn или EMBED_PG_DSN либо DB_HOST,...")

    cfg = EmbedConfig(
        model_name=args.model,
        model_path=args.model_path,
        batch_size=args.batch_size,
        normalize=not args.no_normalize,
        max_seq_length=args.max_seq_length,
        include_properties=not args.no_properties,
        include_afterword=args.include_afterword,
    )

    want_json = bool(args.output)
    want_db = bool(dsn) and (args.from_db or args.input is not None)

    if args.input and not want_json and not want_db:
        ap.error("Укажите --output и/или подключение к БД (--pg-dsn / EMBED_PG_DSN / DB_*)")

    if args.from_db and not dsn:
        ap.error("Нужен DSN для --from-db")

    model = _load_sentence_model(cfg)
    total_upserted = 0
    total_skipped = 0
    accumulated_items: List[Dict[str, Any]] = []

    if args.from_db:
        assert dsn is not None
        conn = connect_pg(dsn)
        try:
            _register_pgvector(conn)
            last_id = 0
            while True:
                with conn.cursor() as cur:
                    batch_rows = fetch_recipe_batch_from_db(
                        cur,
                        last_id=last_id,
                        limit=args.db_fetch_batch,
                        only_missing=args.only_missing,
                    )
                if not batch_rows:
                    break
                ids = [r[0] for r in batch_rows]
                recs = [r[1] for r in batch_rows]
                last_id = ids[-1]

                items, vecs = encode_recipe_vectors(recs, cfg, model=model)
                u, sk = embed_to_postgres(
                    recs, vecs, cfg, conn, db_ids=[int(x) for x in ids]
                )
                total_upserted += u
                total_skipped += sk
                if want_json:
                    accumulated_items.extend(items)
        finally:
            conn.close()

        if want_json and args.output:
            result = {
                "model": cfg.model_name,
                "embedding_dim": int(len(accumulated_items[0]["vector"]))
                if accumulated_items
                else 0,
                "normalize": cfg.normalize,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "items": accumulated_items,
            }
            out_p = Path(args.output)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"OK: saved {len(accumulated_items)} vectors -> {args.output}")

        print(f"OK: upserted {total_upserted} embeddings to Postgres (skipped {total_skipped})")
        return

    # --input path
    assert args.input is not None
    recipes = load_recipes(args.input)
    items, arr = encode_recipe_vectors(recipes, cfg, model=model)

    if want_json:
        result = {
            "model": cfg.model_name,
            "embedding_dim": int(len(items[0]["vector"])) if items else 0,
            "normalize": cfg.normalize,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
        }
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OK: saved {len(recipes)} vectors -> {args.output}")

    if dsn:
        conn = connect_pg(dsn)
        try:
            u, sk = embed_to_postgres(recipes, arr, cfg, conn)
            print(f"OK: upserted {u} rows to Postgres (skipped {sk})")
        finally:
            conn.close()


if __name__ == "__main__":
    main()
