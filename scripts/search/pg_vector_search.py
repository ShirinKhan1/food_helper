"""Векторный поиск по recipe_embeddings и загрузка строк recipes."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple

from psycopg2.extras import RealDictCursor


def register_pgvector(conn) -> None:
    from pgvector.psycopg2 import register_vector

    register_vector(conn)


def vector_search_topk(
    cur,
    query_embedding: Sequence[float],
    *,
    model_name: str,
    k: int = 10,
) -> List[Tuple[int, float]]:
    """
    Топ-K по косинусному расстоянию (<=>). Меньше distance — ближе по смыслу.
    Возвращает список (recipe_id, cosine_distance).
    """
    if k < 1:
        return []

    cur.execute(
        """
        SELECT e.recipe_id, e.embedding <=> %s::vector AS dist
        FROM recipe_embeddings e
        INNER JOIN recipes r ON r.id = e.recipe_id
        WHERE e.model = %s
        ORDER BY e.embedding <=> %s::vector
        LIMIT %s
        """,
        (list(query_embedding), model_name, list(query_embedding), k),
    )
    rows = cur.fetchall()
    out: List[Tuple[int, float]] = []
    for row in rows:
        rid, dist = row[0], float(row[1])
        out.append((int(rid), dist))
    return out


def fetch_recipes_by_ids_ordered(
    cur,
    ids: Sequence[int],
    *,
    scores_by_id: Mapping[int, float] | None = None,
) -> List[Dict[str, Any]]:
    """
    Одна выборка из recipes; порядок как в ids. Добавляет similarity и cosine_distance
    (для нормализованных векторов similarity ≈ 1 - cosine_distance).
    Курсор с RealDictCursor — строки уже словари.
    """
    id_list = list(ids)
    if not id_list:
        return []

    cur.execute(
        """
        SELECT
          id, recipe_url, source, title, description, servings,
          category, subcategory, subcategory_url, afterword,
          calories_kcal, protein_g, fat_g, carbs_g,
          nutrition, properties, ingredients, steps, raw,
          created_at
        FROM recipes
        WHERE id = ANY(%s)
        """,
        (id_list,),
    )
    rows = cur.fetchall()
    by_id: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        d = dict(row)
        by_id[int(d["id"])] = d

    ordered: List[Dict[str, Any]] = []
    for rid in id_list:
        base = by_id.get(rid)
        if base is None:
            continue
        row = dict(base)
        if scores_by_id is not None and rid in scores_by_id:
            dist = float(scores_by_id[rid])
            row["cosine_distance"] = dist
            row["similarity"] = 1.0 - dist
        ordered.append(row)
    return ordered


def search_topk_enriched(
    conn,
    query_embedding: Sequence[float],
    *,
    model_name: str,
    k: int = 10,
) -> List[Dict[str, Any]]:
    """
    Векторный top-K + полные строки recipes в порядке ранжирования.
    """
    register_pgvector(conn)
    with conn.cursor() as cur:
        ranked = vector_search_topk(
            cur,
            query_embedding,
            model_name=model_name,
            k=k,
        )
        if not ranked:
            return []
        ids = [r for r, _ in ranked]
        scores_by_id: Dict[int, float] = {r: d for r, d in ranked}

    with conn.cursor(cursor_factory=RealDictCursor) as rcur:
        return fetch_recipes_by_ids_ordered(
            rcur,
            ids,
            scores_by_id=scores_by_id,
        )
