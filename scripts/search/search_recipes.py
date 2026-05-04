from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np
from sentence_transformers import SentenceTransformer

from scripts.embedding.embed_recipes import EmbedConfig
from scripts.embedding.pg_dsn import connect_pg, resolve_pg_dsn
from scripts.search.pg_vector_search import search_topk_enriched
from scripts.search.query_encode import (
    encode_query,
    load_sentence_transformer,
    should_use_e5_prefix,
)
from scripts.search.query_normalize import normalize_query_for_search


def load_embeddings_json(path: str | Path) -> Tuple[str, bool, List[Dict[str, Any]], np.ndarray]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))

    model_name = data["model"]
    normalize = bool(data.get("normalize", True))
    items = data["items"]

    vectors = np.asarray([it["vector"] for it in items], dtype=np.float32)
    if vectors.ndim != 2:
        raise ValueError("vectors must be a 2D array")

    return model_name, normalize, items, vectors


def topk_similar(
    q: np.ndarray,
    vectors: np.ndarray,
    *,
    top_k: int,
    normalized_vectors: bool,
) -> Tuple[np.ndarray, np.ndarray]:
    n = vectors.shape[0]
    k = min(max(1, top_k), n)

    if normalized_vectors:
        scores = vectors @ q
    else:
        v_norms = np.linalg.norm(vectors, axis=1) + 1e-12
        q_norm = float(np.linalg.norm(q) + 1e-12)
        scores = (vectors @ q) / (v_norms * q_norm)

    idx = np.argpartition(-scores, k - 1)[:k]
    idx = idx[np.argsort(-scores[idx])]
    return idx, scores[idx]


def prepare_search_text(raw: str, *, skip_normalize: bool) -> str:
    if skip_normalize:
        return " ".join(raw.split())
    norm = normalize_query_for_search(raw)
    if norm:
        return norm
    return " ".join(raw.split())


def render_item(it: Dict[str, Any]) -> Tuple[str, str]:
    payload = it.get("payload") or {}
    title = str(payload.get("title") or "").strip()
    url = str(payload.get("recipe_url") or it.get("id") or "").strip()
    return title or "(без названия)", url


def run_user_recipe_search_pg(
    conn,
    model: SentenceTransformer,
    *,
    user_query: str,
    model_name: str | None = None,
    top_k: int = 10,
    normalize_embeddings: bool = True,
    skip_query_normalize: bool = False,
) -> List[Dict[str, Any]]:
    """
    Пайплайн как у пользователя: нормализация текста → эмбеддинг запроса → топ-K из БД + обогащение.
    """
    resolved_name = model_name or EmbedConfig.model_name
    use_e5 = should_use_e5_prefix(resolved_name)
    q = prepare_search_text(user_query.strip(), skip_normalize=skip_query_normalize)
    q_vec = encode_query(
        model,
        q,
        normalize=normalize_embeddings,
        use_e5_prefix=use_e5,
    )
    return search_topk_enriched(
        conn,
        q_vec.tolist(),
        model_name=resolved_name,
        k=top_k,
    )


def print_enriched(rows: List[Dict[str, Any]], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        return
    for rank, row in enumerate(rows, start=1):
        sim = row.get("similarity")
        title = (row.get("title") or "").strip() or "(без названия)"
        url = (row.get("recipe_url") or "").strip()
        score_s = f"{float(sim):+.4f}" if isinstance(sim, (int, float)) else ""
        rid = row.get("id")
        print(f"{rank:>2}. {score_s}  {title}  id={rid}")
        if url:
            print(f"    {url}")


def _configure_model(model: SentenceTransformer) -> None:
    model.max_seq_length = EmbedConfig.max_seq_length


def interactive_loop(
    model: SentenceTransformer,
    items: List[Dict[str, Any]],
    vectors: np.ndarray,
    *,
    top_k: int,
    normalize: bool,
    use_e5_prefix: bool,
    skip_query_normalize: bool,
) -> None:
    print("Вводи запрос (пустая строка — выход):")
    while True:
        try:
            q_raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not q_raw:
            return

        q = prepare_search_text(q_raw, skip_normalize=skip_query_normalize)
        q_vec = encode_query(model, q, normalize=normalize, use_e5_prefix=use_e5_prefix)
        idx, scores = topk_similar(q_vec, vectors, top_k=top_k, normalized_vectors=normalize)

        for rank, (i, s) in enumerate(zip(idx.tolist(), scores.tolist()), start=1):
            title, url = render_item(items[i])
            print(f"{rank:>2}. {s:+.4f}  {title}")
            if url:
                print(f"    {url}")
        print()


def interactive_loop_pg(
    conn,
    model: SentenceTransformer,
    *,
    model_name: str,
    top_k: int,
    normalize: bool,
    skip_query_normalize: bool,
    as_json: bool,
) -> None:
    print("Вводи запрос (пустая строка — выход), режим Postgres:")
    while True:
        try:
            q_raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not q_raw:
            return

        rows = run_user_recipe_search_pg(
            conn,
            model,
            user_query=q_raw,
            model_name=model_name,
            top_k=top_k,
            normalize_embeddings=normalize,
            skip_query_normalize=skip_query_normalize,
        )
        print_enriched(rows, as_json=as_json)
        print()


def main() -> None:
    ap = argparse.ArgumentParser(description="Поиск рецептов: embeddings.json или Postgres (pgvector).")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--embeddings",
        default=None,
        help="Путь к embeddings.json",
    )
    mode.add_argument(
        "--from-db",
        action="store_true",
        help="Искать в Postgres (recipe_embeddings), нужен DSN",
    )
    ap.add_argument(
        "--pg-dsn",
        default=None,
        help="Строка подключения psycopg2 или EMBED_PG_DSN / DB_*",
    )
    ap.add_argument("--top-k", type=int, default=10, help="Сколько результатов")
    ap.add_argument("--query", default=None, help="Один запрос (иначе интерактивный режим)")
    ap.add_argument(
        "--model",
        default=None,
        help="Модель HF (офлайн: переопределяет поле model в JSON; БД: должна совпадать с recipe_embeddings.model)",
    )
    ap.add_argument(
        "--no-normalize",
        action="store_true",
        help="Не нормализовать вектор запроса при encode (если в БД без L2-norm)",
    )
    ap.add_argument(
        "--skip-query-normalize",
        action="store_true",
        help="Не применять лемматизацию/стоп-слова к тексту запроса",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Печать полных строк recipes в JSON (удобно для отладки)",
    )
    args = ap.parse_args()

    normalize_embeddings = not args.no_normalize

    if args.from_db:
        dsn = resolve_pg_dsn(args.pg_dsn)
        if not dsn:
            ap.error("Для --from-db укажите --pg-dsn или настройте EMBED_PG_DSN / DB_HOST")
        model_name = args.model or EmbedConfig.model_name
        model = load_sentence_transformer(model_name)
        _configure_model(model)

        conn = connect_pg(dsn)
        try:
            if args.query is not None:
                q_raw = args.query.strip()
                rows = run_user_recipe_search_pg(
                    conn,
                    model,
                    user_query=q_raw,
                    model_name=model_name,
                    top_k=args.top_k,
                    normalize_embeddings=normalize_embeddings,
                    skip_query_normalize=args.skip_query_normalize,
                )
                print_enriched(rows, as_json=args.json)
                return

            interactive_loop_pg(
                conn,
                model,
                model_name=model_name,
                top_k=args.top_k,
                normalize=normalize_embeddings,
                skip_query_normalize=args.skip_query_normalize,
                as_json=args.json,
            )
        finally:
            conn.close()
        return

    if not args.embeddings:
        ap.error("Укажите --embeddings PATH для офлайн-поиска")
    model_name, normalize_meta, items, vectors = load_embeddings_json(args.embeddings)
    if args.model:
        model_name = args.model

    model = load_sentence_transformer(model_name)
    _configure_model(model)

    use_e5_prefix = should_use_e5_prefix(model_name)
    normalize_vec = normalize_meta if not args.no_normalize else False

    if args.query is not None:
        q_raw = args.query.strip()
        q = prepare_search_text(q_raw, skip_normalize=args.skip_query_normalize)
        q_vec = encode_query(model, q, normalize=normalize_vec, use_e5_prefix=use_e5_prefix)
        idx, scores = topk_similar(q_vec, vectors, top_k=args.top_k, normalized_vectors=normalize_vec)

        for rank, (i, s) in enumerate(zip(idx.tolist(), scores.tolist()), start=1):
            title, url = render_item(items[i])
            print(f"{rank:>2}. {s:+.4f}  {title}")
            if url:
                print(f"    {url}")
        return

    interactive_loop(
        model,
        items,
        vectors,
        top_k=args.top_k,
        normalize=normalize_vec,
        use_e5_prefix=use_e5_prefix,
        skip_query_normalize=args.skip_query_normalize,
    )


if __name__ == "__main__":
    main()
